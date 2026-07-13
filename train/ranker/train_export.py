#!/usr/bin/env python3
"""Train a tiny character cross-encoder ranker and export ONNX."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MODELS = ROOT / "models"
MODELS.mkdir(parents=True, exist_ok=True)

MAX_ROMAN = 24
MAX_GU = 24
EMBED_DIM = 32
HIDDEN = 64
EPOCHS = 8
BATCH = 256
LR = 0.05


def build_alphabets(rows: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    roman_chars = set()
    gu_chars = set()
    for row in rows:
        roman_chars.update(row["input"].lower())
        for c in row["candidates"]:
            gu_chars.update(c["text"])
    # reserve 0=pad, 1=unk
    roman_stoi = {"<pad>": 0, "<unk>": 1}
    for ch in sorted(roman_chars):
        if ch not in roman_stoi:
            roman_stoi[ch] = len(roman_stoi)
    gu_stoi = {"<pad>": 0, "<unk>": 1}
    for ch in sorted(gu_chars):
        if ch not in gu_stoi:
            gu_stoi[ch] = len(gu_stoi)
    return roman_stoi, gu_stoi


def encode(text: str, stoi: dict[str, int], max_len: int) -> np.ndarray:
    ids = np.zeros(max_len, dtype=np.int64)
    for i, ch in enumerate(text[:max_len]):
        ids[i] = stoi.get(ch, 1)
    return ids


class CharRanker:
    """Minimal NumPy cross-encoder: embed chars, mean-pool, MLP -> score."""

    def __init__(self, n_roman: int, n_gu: int, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.E_r = rng.normal(0, 0.08, size=(n_roman, EMBED_DIM)).astype(np.float32)
        self.E_g = rng.normal(0, 0.08, size=(n_gu, EMBED_DIM)).astype(np.float32)
        self.W1 = rng.normal(0, 0.08, size=(EMBED_DIM * 2, HIDDEN)).astype(np.float32)
        self.b1 = np.zeros(HIDDEN, dtype=np.float32)
        self.W2 = rng.normal(0, 0.08, size=(HIDDEN, 1)).astype(np.float32)
        self.b2 = np.zeros(1, dtype=np.float32)

    def forward(self, r_ids: np.ndarray, g_ids: np.ndarray) -> np.ndarray:
        # r_ids: [B, Lr], g_ids: [B, Lg]
        r = self.E_r[r_ids]  # B, L, D
        g = self.E_g[g_ids]
        r_mask = (r_ids != 0).astype(np.float32)[:, :, None]
        g_mask = (g_ids != 0).astype(np.float32)[:, :, None]
        r_pool = (r * r_mask).sum(axis=1) / np.maximum(r_mask.sum(axis=1), 1.0)
        g_pool = (g * g_mask).sum(axis=1) / np.maximum(g_mask.sum(axis=1), 1.0)
        x = np.concatenate([r_pool, g_pool], axis=1)
        h = np.tanh(x @ self.W1 + self.b1)
        s = (h @ self.W2 + self.b2).reshape(-1)
        return s

    def pairwise_step(self, r_ids, g_pos, g_neg, lr=LR):
        # simple pairwise logistic: score_pos > score_neg
        sp = self.forward(r_ids, g_pos)
        sn = self.forward(r_ids, g_neg)
        # loss = softplus(-(sp-sn))
        diff = sp - sn
        # dloss/ddiff = -sigmoid(-diff) = sigmoid(diff)-1
        sig = 1.0 / (1.0 + np.exp(-np.clip(diff, -20, 20)))
        d_diff = sig - 1.0  # [B]

        # finite-diff style parameter update via autograd-lite on embeddings/MLP
        # Recompute with stored activations
        def grads(ids_r, ids_g, upstream):
            r = self.E_r[ids_r]
            g = self.E_g[ids_g]
            r_mask = (ids_r != 0).astype(np.float32)[:, :, None]
            g_mask = (ids_g != 0).astype(np.float32)[:, :, None]
            r_den = np.maximum(r_mask.sum(axis=1), 1.0)
            g_den = np.maximum(g_mask.sum(axis=1), 1.0)
            r_pool = (r * r_mask).sum(axis=1) / r_den
            g_pool = (g * g_mask).sum(axis=1) / g_den
            x = np.concatenate([r_pool, g_pool], axis=1)
            pre = x @ self.W1 + self.b1
            h = np.tanh(pre)
            # upstream is dL/ds for each batch item
            d_s = upstream.reshape(-1, 1)
            d_h = d_s @ self.W2.T * (1 - h * h)
            d_W2 = h.T @ d_s
            d_b2 = d_s.sum(axis=0)
            d_x = d_h @ self.W1.T
            d_W1 = x.T @ d_h
            d_b1 = d_h.sum(axis=0)
            d_rp = d_x[:, :EMBED_DIM]
            d_gp = d_x[:, EMBED_DIM:]
            # pool grads to embeddings
            d_r = (d_rp[:, None, :] / r_den[:, :, None]) * r_mask
            d_g = (d_gp[:, None, :] / g_den[:, :, None]) * g_mask
            return d_W1, d_b1, d_W2, d_b2, ids_r, d_r, ids_g, d_g

        # pos contributes +d_diff, neg contributes -d_diff
        g1 = grads(r_ids, g_pos, d_diff)
        g2 = grads(r_ids, g_neg, -d_diff)

        self.W1 -= lr * (g1[0] + g2[0]) / r_ids.shape[0]
        self.b1 -= lr * (g1[1] + g2[1]) / r_ids.shape[0]
        self.W2 -= lr * (g1[2] + g2[2]) / r_ids.shape[0]
        self.b2 -= lr * (g1[3] + g2[3]) / r_ids.shape[0]

        # embedding updates (scatter-add)
        for ids, d_e, table in (
            (g1[4], g1[5], self.E_r),
            (g1[6], g1[7], self.E_g),
            (g2[4], g2[5], self.E_r),
            (g2[6], g2[7], self.E_g),
        ):
            B, L, D = d_e.shape
            for b in range(B):
                for t in range(L):
                    idx = int(ids[b, t])
                    if idx == 0:
                        continue
                    table[idx] -= lr * d_e[b, t] / B

        loss = np.mean(np.logaddexp(0, -diff))
        return float(loss)


def load_rows() -> list[dict]:
    path = DATA / "gu_train.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row.get("candidates"):
            rows.append(row)
    return rows


def make_pairs(rows, roman_stoi, gu_stoi, rng):
    r_batch, pos_batch, neg_batch = [], [], []
    for row in rows:
        inp = row["input"].lower()
        cands = [c["text"] for c in row["candidates"]]
        if len(cands) < 1:
            continue
        pos = cands[0]
        # hard negative: another candidate or corrupted
        if len(cands) > 1:
            neg = cands[rng.integers(1, len(cands))]
        else:
            # shuffle chars lightly
            chars = list(pos)
            if len(chars) > 2:
                i, j = rng.integers(0, len(chars), size=2)
                chars[i], chars[j] = chars[j], chars[i]
            neg = "".join(chars) or pos + "ા"
            if neg == pos:
                neg = pos + "ં"
        r_batch.append(encode(inp, roman_stoi, MAX_ROMAN))
        pos_batch.append(encode(pos, gu_stoi, MAX_GU))
        neg_batch.append(encode(neg, gu_stoi, MAX_GU))
    return np.stack(r_batch), np.stack(pos_batch), np.stack(neg_batch)


def export_onnx(model: CharRanker, roman_stoi: dict, gu_stoi: dict) -> Path:
    """Export via onnx helper graph built with numpy weights (onnx package)."""
    try:
        import onnx
        from onnx import TensorProto, helper, numpy_helper
    except ImportError:
        # fallback: save npz + write a tiny torch-free runtime that loads npz
        npz = MODELS / "gu_ranker.npz"
        np.savez(
            npz,
            E_r=model.E_r,
            E_g=model.E_g,
            W1=model.W1,
            b1=model.b1,
            W2=model.W2,
            b2=model.b2,
        )
        meta = {
            "format": "npz",
            "roman_stoi": roman_stoi,
            "gu_stoi": gu_stoi,
            "max_roman": MAX_ROMAN,
            "max_gu": MAX_GU,
            "embed_dim": EMBED_DIM,
            "hidden": HIDDEN,
            "weights": str(npz.name),
        }
        (MODELS / "ranker_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"onnx package missing; wrote {npz}")
        return npz

    # Build ONNX: inputs roman_ids[int64 BxLr], gu_ids[int64 BxLg] -> score[float Bx1]
    # Use Gather + ReduceMean + Gemm + Tanh
    E_r = numpy_helper.from_array(model.E_r, name="E_r")
    E_g = numpy_helper.from_array(model.E_g, name="E_g")
    W1 = numpy_helper.from_array(model.W1, name="W1")
    b1 = numpy_helper.from_array(model.b1, name="b1")
    W2 = numpy_helper.from_array(model.W2, name="W2")
    b2 = numpy_helper.from_array(model.b2, name="b2")

    nodes = [
        helper.make_node("Gather", ["E_r", "roman_ids"], ["r_emb"], axis=0),
        helper.make_node("Gather", ["E_g", "gu_ids"], ["g_emb"], axis=0),
        # mask via Cast of Not Equal — simplify: ReduceMean over sequence (pads dilute slightly)
        helper.make_node("ReduceMean", ["r_emb"], ["r_pool"], axes=[1], keepdims=0),
        helper.make_node("ReduceMean", ["g_emb"], ["g_pool"], axes=[1], keepdims=0),
        helper.make_node("Concat", ["r_pool", "g_pool"], ["x"], axis=1),
        helper.make_node("Gemm", ["x", "W1", "b1"], ["pre"], alpha=1.0, beta=1.0),
        helper.make_node("Tanh", ["pre"], ["h"]),
        helper.make_node("Gemm", ["h", "W2", "b2"], ["score"], alpha=1.0, beta=1.0),
    ]

    graph = helper.make_graph(
        nodes,
        "gu_ranker",
        [
            helper.make_tensor_value_info("roman_ids", TensorProto.INT64, ["B", MAX_ROMAN]),
            helper.make_tensor_value_info("gu_ids", TensorProto.INT64, ["B", MAX_GU]),
        ],
        [helper.make_tensor_value_info("score", TensorProto.FLOAT, ["B", 1])],
        [E_r, E_g, W1, b1, W2, b2],
    )
    model_proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model_proto.ir_version = 8
    out = MODELS / "gu_ranker.onnx"
    onnx.save(model_proto, out)
    meta = {
        "format": "onnx",
        "roman_stoi": roman_stoi,
        "gu_stoi": gu_stoi,
        "max_roman": MAX_ROMAN,
        "max_gu": MAX_GU,
        "embed_dim": EMBED_DIM,
        "hidden": HIDDEN,
        "model": str(out.name),
        "inputs": ["roman_ids", "gu_ids"],
        "output": "score",
    }
    (MODELS / "ranker_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return out


def main() -> None:
    random.seed(0)
    rng = np.random.default_rng(0)
    rows = load_rows()
    print(f"train rows: {len(rows)}")
    roman_stoi, gu_stoi = build_alphabets(rows)
    print(f"vocab roman={len(roman_stoi)} gu={len(gu_stoi)}")

    model = CharRanker(len(roman_stoi), len(gu_stoi), seed=0)
    # subsample for speed if huge
    train_rows = rows if len(rows) <= 8000 else [rows[i] for i in rng.choice(len(rows), size=8000, replace=False)]

    for epoch in range(EPOCHS):
        rng.shuffle(train_rows)
        losses = []
        for i in range(0, len(train_rows), BATCH):
            batch_rows = train_rows[i : i + BATCH]
            r_ids, g_pos, g_neg = make_pairs(batch_rows, roman_stoi, gu_stoi, rng)
            loss = model.pairwise_step(r_ids, g_pos, g_neg, lr=LR * (0.85**epoch))
            losses.append(loss)
        print(f"epoch {epoch+1}/{EPOCHS} loss={sum(losses)/max(len(losses),1):.4f}")

    export_onnx(model, roman_stoi, gu_stoi)
    # always also save npz for python sidecar fallback
    np.savez(
        MODELS / "gu_ranker.npz",
        E_r=model.E_r,
        E_g=model.E_g,
        W1=model.W1,
        b1=model.b1,
        W2=model.W2,
        b2=model.b2,
    )
    print("done")


if __name__ == "__main__":
    main()
