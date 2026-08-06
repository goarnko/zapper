#!/usr/bin/env bash
# Build an AppImage for ZapTV.
#
# IMPORTANT: this is a *thin* AppImage. It bundles ZapTV itself but uses the
# host's python3, Tkinter and Pillow rather than shipping an interpreter, so
# it is not self-contained the way an AppImage usually implies. AppRun says
# so plainly when a dependency is missing. Bundling CPython and Tk properly
# would mean building on a python-appimage base; see MILESTONE 7 notes in
# CLAUDE.md before changing this.
#
#   packaging/build-appimage.sh   -> dist/ZapTV-<version>-x86_64.AppImage
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
version="$(python3 -c "import re,pathlib; print(re.search(r'\"(.*)\"', pathlib.Path('$root/src/zaptv/__init__.py').read_text()).group(1))")"

appdir="$root/build/ZapTV.AppDir"
tools="$root/build/tools"
out="$root/dist"
rm -rf "$appdir"
mkdir -p "$appdir" "$tools" "$out"

# --- AppDir ----------------------------------------------------------------
mkdir -p "$appdir/usr/lib/python3/dist-packages"
cp -r "$root/src/zaptv" "$appdir/usr/lib/python3/dist-packages/zaptv"
find "$appdir" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

install -Dm644 "$here/zaptv.desktop" "$appdir/zaptv.desktop"
install -Dm644 "$here/icons/256x256/zaptv.png" "$appdir/zaptv.png"
install -Dm644 "$here/icons/256x256/zaptv.png" \
    "$appdir/usr/share/icons/hicolor/256x256/apps/zaptv.png"

cat > "$appdir/AppRun" <<'APPRUN'
#!/bin/sh
# Thin AppImage: ZapTV travels with the bundle, its runtime does not.
here="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$here/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ZapTV needs python3 on this system." >&2
    exit 1
fi
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "ZapTV needs Tkinter: sudo apt install python3-tk" >&2
    exit 1
fi
if ! python3 -c "import PIL" >/dev/null 2>&1; then
    echo "ZapTV needs Pillow: sudo apt install python3-pil" >&2
    exit 1
fi
exec python3 -m zaptv "$@"
APPRUN
chmod 755 "$appdir/AppRun"

# --- appimagetool ----------------------------------------------------------
tool="$tools/appimagetool"
if [ ! -x "$tool" ]; then
    url="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    echo "Fetching appimagetool..." >&2
    curl -fsSL -o "$tools/appimagetool.AppImage" "$url"
    chmod +x "$tools/appimagetool.AppImage"
    # Extract rather than run it: AppImages need FUSE, which many systems
    # (and every container) lack.
    (cd "$tools" && ./appimagetool.AppImage --appimage-extract >/dev/null)
    ln -sf "$tools/squashfs-root/AppRun" "$tool"
fi

target="$out/ZapTV-${version}-x86_64.AppImage"
ARCH=x86_64 "$tool" --no-appstream "$appdir" "$target" >/dev/null 2>&1
echo "$target"
