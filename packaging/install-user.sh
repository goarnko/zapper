#!/usr/bin/env bash
# Install ZapTV for the current user only — no root, no packaging.
#
# Puts a launcher on PATH and registers the desktop entry and icons, with
# the code left where it is, so a git pull updates the installed app.
#
#   packaging/install-user.sh            install
#   packaging/install-user.sh --uninstall
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"

bin="${XDG_BIN_HOME:-$HOME/.local/bin}"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$bin/zaptv" "$apps/zaptv.desktop"
    find "$icons" -name 'zaptv.png' -delete 2>/dev/null || true
    update-desktop-database -q "$apps" 2>/dev/null || true
    echo "Removed ZapTV from $bin and $apps"
    exit 0
fi

mkdir -p "$bin" "$apps"

# The launcher points back at this checkout rather than copying it, so the
# installed app tracks the working tree.
cat > "$bin/zaptv" <<LAUNCHER
#!/bin/sh
export PYTHONPATH="$root/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m zaptv "\$@"
LAUNCHER
chmod 755 "$bin/zaptv"

# Exec must be absolute: the desktop session does not inherit a shell PATH.
sed "s|^Exec=zaptv$|Exec=$bin/zaptv|" "$here/zaptv.desktop" > "$apps/zaptv.desktop"

for dir in "$here"/icons/*/; do
    size="$(basename "$dir")"
    install -Dm644 "$dir/zaptv.png" "$icons/$size/apps/zaptv.png"
done

update-desktop-database -q "$apps" 2>/dev/null || true
gtk-update-icon-cache -q -f "$icons" 2>/dev/null || true

echo "Installed launcher: $bin/zaptv"
echo "Desktop entry:      $apps/zaptv.desktop"
case ":$PATH:" in
    *":$bin:"*) ;;
    *) echo "Note: $bin is not on your PATH; add it to run 'zaptv' from a terminal." ;;
esac
