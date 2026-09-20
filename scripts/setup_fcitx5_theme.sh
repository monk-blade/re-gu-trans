#!/usr/bin/env bash
# Install the Ori fcitx5 theme and set the classic-UI candidate panel to use
# Noto Serif Gujarati (falling back to a Latin-covering font for roman echo
# candidates and English annotations). User-space only; no root required.
set -euo pipefail

THEME_REPO="https://github.com/Reverier-Xu/Ori-fcitx5.git"
THEMES_DIR="${HOME}/.local/share/fcitx5/themes"
CONF_DIR="${HOME}/.config/fcitx5/conf"
VARIANT="${1:-OriDark}"
LATIN_FONT="${LATIN_FALLBACK_FONT:-Noto Sans 11}"

case "$VARIANT" in
  OriDark|OriLight) ;;
  *) echo "usage: $0 [OriDark|OriLight]" >&2; exit 2 ;;
esac

if ! fc-list | grep -qi "Noto Serif Gujarati"; then
  echo "WARNING: Noto Serif Gujarati not found by fontconfig." >&2
  echo "  Fedora/RHEL: sudo dnf install google-noto-serif-gujarati-fonts" >&2
  echo "  Debian/Ubuntu: sudo apt install fonts-noto-core" >&2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Cloning $THEME_REPO ..."
git clone --depth 1 "$THEME_REPO" "$TMP/Ori-fcitx5" >/dev/null 2>&1

mkdir -p "$THEMES_DIR"
cp -r "$TMP/Ori-fcitx5/OriDark" "$TMP/Ori-fcitx5/OriLight" "$THEMES_DIR/"
echo "Installed OriDark and OriLight to $THEMES_DIR"

mkdir -p "$CONF_DIR"
cat > "$CONF_DIR/classicui.conf" <<EOF
[Appearance]
Theme=$VARIANT
DarkTheme=$VARIANT
UseDarkThemeWhenSystemDefaultIsDark=False
Font="Noto Serif Gujarati,$LATIN_FONT"
MenuFont="$LATIN_FONT"
TrayFont="Sans 10"
PreferTextIcon=False
ShowLayoutNameInIcon=True
UseInputMethodLanguageToDisplayText=True
WheelHasEffect=True
PerScreenDPI=False
Vertical Candidate List=False
EOF
echo "Wrote $CONF_DIR/classicui.conf (theme=$VARIANT, candidate font=Noto Serif Gujarati)"

if pgrep -x fcitx5 >/dev/null 2>&1; then
  echo "Restart fcitx5 to apply: pkill fcitx5 && setsid fcitx5 -d &"
else
  echo "Start fcitx5 to apply: setsid fcitx5 -d &"
fi
