#!/bin/bash
# Build DivyInvestorPro.app and a drag-to-Applications DMG into dist/.
# Usage: ./build_mac.sh   (expects the .venv from the README)
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
NAME=DivyInvestorPro
VERSION=$($PY -c "import divyinvestorpro; print(divyinvestorpro.__version__)")
APP="dist/$NAME.app"
DMG="dist/$NAME-$VERSION-Mac.dmg"

echo "==> Tests"
$PY -m unittest discover -s tests -q

echo "==> Icon"
$PY tools/make_icon.py "build/$NAME.icns"

echo "==> App bundle"
$PY -m PyInstaller --noconfirm --clean --windowed --log-level WARN \
    --name "$NAME" \
    --icon "build/$NAME.icns" \
    --osx-bundle-identifier com.divyinvestorpro.app \
    run.py

plutil -replace CFBundleShortVersionString -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$VERSION" "$APP/Contents/Info.plist"
plutil -replace NSHumanReadableCopyright -string "DivyInvestorPro" "$APP/Contents/Info.plist"
# Ad-hoc signature (no Apple Developer ID). Re-sign after editing Info.plist.
codesign --force --deep --sign - "$APP"

echo "==> Disk image"
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -quiet -volname "$NAME $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo "==> Done: $DMG ($(du -h "$DMG" | cut -f1))"
