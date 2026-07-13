# packaging/

Cross-platform package definitions for **re-gu-trans** (schema + librime-qjs plugin).

## Layout

| Path | Role |
|------|------|
| `nfpm.yaml` | deb + rpm metadata (version `__VERSION__` substituted at build) |
| `linux/postinst.sh` | post-install notice + best-effort fcitx reload |
| `linux/re-gu-trans-enable` | user helper to copy schema into Fcitx5/IBus Rime dir |
| `../scripts/package/` | stage + per-OS build scripts |

## Pin

- `LIBRIME_QJS_TAG=v1.3.0`
- `LIBRIME_TAG=1.16.1`

## CI

Push a tag `vX.Y.Z` → `.github/workflows/release-packages.yml` publishes GitHub Release assets.

```bash
git tag v2.6.0
git push origin v2.6.0
```
