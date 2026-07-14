# Patch notes: Environment.writeFileAtomic for librime-qjs

Pin librime-qjs to the release tag in `scripts/package/common.sh` (`LIBRIME_QJS_TAG`)
and `vendor/librime-qjs/version-info.txt` (must match).

## Required API

```cpp
// Environment::writeFileAtomic(path, content)
// - path must resolve under userDataDir (reject .. / absolute escape)
// - write to path + ".tmp.<pid>" then rename
// - POSIX mode 0600
// - throw / return error on failure
```

Until the patched dylib is built into packages, JS falls back to `saveFile` / `write`
but still refuses paths outside `userDataDir` when detectable.

Update `vendor/librime-qjs/version-info.txt` after applying the patch and rebuild
macOS / Windows / Linux plugins in CI release jobs.
