#!/bin/sh
# postinst for re-gu-trans (deb/rpm via nfpm)
set -e

echo "re-gu-trans: installed schema, IndicXlit model, librime-qjs plugin,"
echo "             and the Ori fcitx5 theme + Noto Serif Gujarati candidate font."

TARGET_USER=""
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
  TARGET_USER="$SUDO_USER"
elif [ -n "${PKEXEC_UID:-}" ]; then
  TARGET_USER="$(getent passwd "$PKEXEC_UID" 2>/dev/null | cut -d: -f1 || true)"
fi

if [ -n "$TARGET_USER" ] && command -v runuser >/dev/null 2>&1; then
  echo "re-gu-trans: enabling Gujarati for user '$TARGET_USER' ..."
  if runuser -l "$TARGET_USER" -c 're-gu-trans-enable' 2>/dev/null; then
    if runuser -l "$TARGET_USER" -c 'command -v fcitx5-remote >/dev/null 2>&1'; then
      runuser -l "$TARGET_USER" -c 'fcitx5-remote -r' >/dev/null 2>&1 || \
        echo "re-gu-trans: fcitx5 not running yet for $TARGET_USER; it will pick this up on next login."
    fi
    echo "re-gu-trans: done. Select Rime -> Gujarati Transliteration in fcitx5 if it isn't already active."
  else
    echo "re-gu-trans: could not auto-enable for '$TARGET_USER' (no active session?)."
    echo "             Run 're-gu-trans-enable' as that user, then restart fcitx5."
  fi
else
  echo "re-gu-trans: run 're-gu-trans-enable' as your normal user to enable the schema,"
  echo "             then Deploy / restart fcitx5 or ibus."
fi

exit 0
