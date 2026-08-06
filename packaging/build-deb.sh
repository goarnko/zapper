#!/usr/bin/env bash
# Build a .deb for ZapTV.
#
# Deliberately plain dpkg-deb rather than dpkg-buildpackage: the package is
# pure Python with no compilation, so a staged tree and a control file say
# everything a full debhelper setup would, with far less to go wrong.
#
#   packaging/build-deb.sh          -> dist/zaptv_<version>_all.deb
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
version="$(python3 -c "import re,pathlib; print(re.search(r'\"(.*)\"', pathlib.Path('$root/src/zaptv/__init__.py').read_text()).group(1))")"

stage="$root/build/deb/zaptv_${version}_all"
out="$root/dist"
rm -rf "$stage"
mkdir -p "$stage/DEBIAN" "$out"

# --- payload ---------------------------------------------------------------
site="$stage/usr/lib/python3/dist-packages"
mkdir -p "$site"
cp -r "$root/src/zaptv" "$site/zaptv"
find "$site" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$stage/usr/bin"
cat > "$stage/usr/bin/zaptv" <<'LAUNCHER'
#!/usr/bin/python3
from zaptv.main import main

raise SystemExit(main())
LAUNCHER
chmod 755 "$stage/usr/bin/zaptv"

# --- desktop integration ---------------------------------------------------
install -Dm644 "$here/zaptv.desktop" "$stage/usr/share/applications/zaptv.desktop"
for dir in "$here"/icons/*/; do
    size="$(basename "$dir")"
    install -Dm644 "$dir/zaptv.png" \
        "$stage/usr/share/icons/hicolor/$size/apps/zaptv.png"
done
install -Dm644 "$root/LICENSE" "$stage/usr/share/doc/zaptv/copyright"

# --- control ---------------------------------------------------------------
# Installed-Size is in KiB and advisory; dpkg warns if it is absent.
size_kb="$(du -sk "$stage" | cut -f1)"
cat > "$stage/DEBIAN/control" <<CONTROL
Package: zaptv
Version: ${version}
Section: video
Priority: optional
Architecture: all
Maintainer: goarnko <goarnko@gmail.com>
Installed-Size: ${size_kb}
Depends: python3 (>= 3.10), python3-tk, python3-pil
Recommends: vlc | mpv, xdg-utils
Homepage: https://github.com/goarnko/zapper
Description: Fast launcher for live TV channels
 ZapTV lists live TV channels and hands the selected one to VLC or mpv.
 It downloads its channel lists at runtime and ships none of its own.
 .
 Includes search, favorites, recently watched, a now/next guide from
 XMLTV, and channel logos.
CONTROL

cat > "$stage/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    # Best effort: the app works without either cache being refreshed.
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
    gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
fi
POSTINST
chmod 755 "$stage/DEBIAN/postinst"

# postrm gets remove/purge/upgrade, never "configure" — it needs its own
# script rather than a copy of postinst, or the caches keep a dead entry.
cat > "$stage/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
case "$1" in
    remove|purge)
        update-desktop-database -q /usr/share/applications 2>/dev/null || true
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
        ;;
esac
POSTRM
chmod 755 "$stage/DEBIAN/postrm"

deb="$out/zaptv_${version}_all.deb"
fakeroot dpkg-deb --build "$stage" "$deb" >/dev/null
echo "$deb"
