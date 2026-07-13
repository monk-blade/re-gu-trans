#!/bin/sh
# postinst for re-gu-trans (deb/rpm via nfpm)
set -e

echo "re-gu-trans: installed schema into /usr/share/rime-data and librime-qjs plugin."
echo "re-gu-trans: run 're-gu-trans-enable' as your normal user to enable the schema,"
echo "             then Deploy / restart fcitx5 or ibus."

if command -v fcitx5-remote >/dev/null 2>&1; then
  fcitx5-remote -r >/dev/null 2>&1 || true
fi

exit 0
