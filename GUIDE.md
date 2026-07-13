# GUIDE.md — Install re-gu-trans on macOS, Windows & Linux

End-to-end setup for the Gujarati Rime IME (lexicon ranking + QuickJS plugins).

## Requirements

| Piece | Why |
|-------|-----|
| Rime frontend | **Squirrel** (macOS), **Weasel** (Windows), **fcitx5-rime** or **ibus-rime** (Linux) |
| **librime-qjs** | Loads `js/*.js` translators/processors (bundled in Release packages) |
| Schema + lexicon | Shipped in packages or synced from this repo |

Pinned plugin for Release packages: **librime-qjs v1.3.0** (librime **1.16.1**). Use a recent Squirrel / Weasel build.

Optional: Python 3 + ONNX Runtime for the local ranker sidecar (not required for ranking).

---

## Install from GitHub Releases (recommended)

Download assets from [Releases](https://github.com/monk-blade/re-gu-trans/releases). Packages install the schema/lexicon/JS **and** a compatible librime-qjs plugin. They do **not** install the Rime frontend itself.

### macOS (Apple Silicon)

1. Install [Squirrel](https://github.com/rime/squirrel/releases).
2. Open `re-gu-trans-<ver>-macos-arm64.pkg`, **or** unzip the `.zip` and run:

```bash
sudo ./install.sh
```

3. System Settings → Keyboard → Input Sources → enable **Squirrel**, then select **Gujarati**.
4. Deploy once from the Squirrel menu (⟲) if needed.

User dir: `~/Library/Rime/`

**Intel Macs:** upstream librime-qjs currently publishes **ARM64 only**. Build the plugin from source or use the from-source steps below.

### Windows (x64)

1. Install [Weasel (小狼毫)](https://github.com/rime/weasel/releases).
2. Exit Weasel from the system tray.
3. Unzip `re-gu-trans-<ver>-windows-x64.zip`.
4. Right-click `install.bat` → **Run as administrator** (or `powershell -ExecutionPolicy Bypass -File install.ps1`).
5. Deploy from the Weasel tray menu; select **Gujarati Transliteration**.

User dir: `%APPDATA%\Rime\`  
The installer backs up the previous `rime.dll` as `rime.dll.re-gu-trans.bak`.

### Linux (amd64) — deb / rpm

1. Install a Rime frontend (`fcitx5-rime` or `ibus-rime`).
2. Install the package:

```bash
# Debian / Ubuntu
sudo apt install ./re-gu-trans_<ver>_amd64.deb

# Fedora / RHEL
sudo dnf install ./re-gu-trans-<ver>*.rpm
```

3. Enable the schema as your normal user:

```bash
re-gu-trans-enable
```

4. Deploy / restart (`fcitx5-remote -r` or `ibus restart`) and select **Gujarati Transliteration**.

Plugin lands in `/usr/lib/rime-plugins/` (and the Debian multiarch path). Shared data: `/usr/share/rime-data/`.

---

## From source (developers)

### macOS (Squirrel)

```bash
git clone https://github.com/monk-blade/re-gu-trans.git
cd re-gu-trans
./scripts/install_librime_qjs.sh   # admin password; installs librime-qjs.dylib
python3 scripts/build_gu_word_freq.py   # if unigram/stems missing
./scripts/sync_rime.sh
```

### Linux

#### 1. Install a Rime frontend

**Fcitx5 (recommended):**

```bash
# Debian/Ubuntu
sudo apt install fcitx5 fcitx5-rime fcitx5-config-qt

# Fedora
sudo dnf install fcitx5 fcitx5-rime fcitx5-configtool

# Arch
sudo pacman -S fcitx5-im fcitx5-rime
```

Set env (usually in `~/.pam_environment` or your session):

```bash
export GTK_IM_MODULE=fcitx
export QT_IM_MODULE=fcitx
export XMODIFIERS=@im=fcitx
```

**IBus:**

```bash
# Debian/Ubuntu
sudo apt install ibus ibus-rime

# Arch
sudo pacman -S ibus-rime
```

#### 2. Install librime-qjs

Prefer the **deb/rpm** from Releases. To build the plugin yourself, see [librime-qjs build-linux](https://github.com/HuangJian/librime-qjs/blob/main/doc/build-linux.md) or:

```bash
./scripts/package/linux/build_librime_qjs.sh
sudo mkdir -p /usr/local/lib/rime-plugins
sudo cp dist/plugins/librime-qjs.so /usr/local/lib/rime-plugins/
```

#### 3. Deploy this project

```bash
python3 scripts/build_gu_word_freq.py   # if needed
./scripts/sync_rime.sh
```

`sync_rime.sh` auto-detects:

| Frontend | User data directory |
|----------|---------------------|
| Fcitx5 | `~/.local/share/fcitx5/rime` |
| IBus | `~/.config/ibus/rime` |
| Override | `RIME_USER_DIR=/path ./scripts/sync_rime.sh` |

### Windows (from source)

1. Install Weasel and a librime-qjs Windows package from [HuangJian/librime-qjs releases](https://github.com/HuangJian/librime-qjs/releases) (replace `rime.dll` as documented upstream).
2. Copy `rime/*` into `%APPDATA%\Rime\` (include `js/` and `js/lm/`).
3. Ensure `default.custom.yaml` lists `schema: gujarati`, then Deploy.

---

## Optional ONNX ranker

```bash
# Linux example
python3 runtime/onnx_ranker/server.py --sock "$HOME/.local/share/fcitx5/rime/run/gu_ranker.sock"
```

Ranking still works without the sidecar (lexicon + unigram only).

---

## Verify

Logs should show:

```text
loaded plugin: qjs
$qjs$ lexicon loaded entries=...
$qjs$ unigram loaded entries=...
```

Smoke tests:

| Type | Expect #1 (approx.) |
|------|---------------------|
| `jamin` | જમીન |
| `favshe` | ફાવશે |
| `poshatu` | પોષતું |
| `ketli` | કેટલી |

Then press **Space** or **`.`** — should commit the highlighted candidate and insert the mark.

### If `.` pages the menu instead of committing

Default Rime binds `period` → `Page_Down` when `has_menu`. This schema runs `commit_on_punct` **before** `key_binder` and keeps `.` / `,` as themselves. Deploy again after installing a Release build.

---

## Building packages (CI / maintainers)

GitHub Actions (`.github/workflows/release-packages.yml`) builds on tags `v*`:

| Asset | Notes |
|-------|--------|
| `*-macos-arm64.pkg` / `.zip` | Downloads HuangJian macOS ARM64 qjs |
| `*-windows-x64.zip` | Downloads HuangJian Windows `rime.dll` |
| `*_amd64.deb` / `*.rpm` | Builds `librime-qjs.so` from source + nfpm |

Local:

```bash
VERSION=2.6.0 ./scripts/package/macos/build_pkg.sh      # macOS only
VERSION=2.6.0 ./scripts/package/windows/build_zip.sh    # needs 7z
VERSION=2.6.0 ./scripts/package/linux/build_packages.sh # needs build deps + nfpm
```

See [packaging/README.md](./packaging/README.md).

More agent/dev notes: [AGENTS.md](./AGENTS.md).
