# Patch: Environment::writeFileAtomic for librime-qjs (v1.3.0 / 7231b4a)

## Required API

```cpp
// Environment::writeFileAtomic(relativeOrAbsUnderUserData, content)
// - Resolve under userDataDir only; reject ".." and absolute escapes
// - Write to path + ".tmp.<pid>" then fsync + rename
// - POSIX mode 0600 (Windows: user-only ACL best effort)
// - Throw JsException on failure
```

## Apply

```bash
# From a clean HuangJian/librime-qjs checkout at LIBRIME_QJS_TAG:
patch -p1 < vendor/librime-qjs/patches/0001-writeFileAtomic.patch
# Then build plugins (see scripts/package/*/build_*.sh).
```

Stop shipping upstream prebuilts that lack `writeFileAtomic` once this lands in release CI.

JS runtime: if `env.writeFileAtomic` is missing, learning stays **disabled** (one warning). No `saveFile` / global `write` fallback.
