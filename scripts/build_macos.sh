#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PRODUCT_NAME="PDF Studio Lite V3.2"
BUNDLE_ID="com.guoshui.pdfstudiolite"
ARCH="${PDFSTUDIO_ARCH:-$(uname -m)}"
ICON_PATH="ui/assets/branding/pdf-toaster-app.icns"
OUTPUT_DIR="$PROJECT_ROOT/release-macos"

export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-14.0}"

"$PYTHON_BIN" -m pytest -q
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "$PRODUCT_NAME" \
  --icon "$ICON_PATH" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --target-architecture "$ARCH" \
  --add-data "ui/assets:ui/assets" \
  --runtime-hook "scripts/pyi_rth_dll_paths.py" \
  --collect-all pymupdf \
  --collect-all pikepdf \
  "app/main.py"

APP_PATH="$PROJECT_ROOT/dist/$PRODUCT_NAME.app"
APP_EXECUTABLE="$APP_PATH/Contents/MacOS/$PRODUCT_NAME"
if [[ ! -x "$APP_EXECUTABLE" ]]; then
  echo "未找到 macOS 应用可执行文件：$APP_EXECUTABLE" >&2
  exit 1
fi

QT_QPA_PLATFORM=offscreen "$APP_EXECUTABLE" --self-test
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/dmg-root"
ditto "$APP_PATH" "$OUTPUT_DIR/dmg-root/$PRODUCT_NAME.app"
ln -s /Applications "$OUTPUT_DIR/dmg-root/Applications"

ARCH_LABEL="$ARCH"
if [[ "$ARCH" == "arm64" ]]; then
  ARCH_LABEL="Apple-Silicon"
elif [[ "$ARCH" == "x86_64" ]]; then
  ARCH_LABEL="Intel"
fi

DMG_PATH="$OUTPUT_DIR/PDF.Studio.Lite.V3.2.macOS-$ARCH_LABEL.dmg"
ZIP_PATH="$OUTPUT_DIR/PDF.Studio.Lite.V3.2.macOS-$ARCH_LABEL.zip"
hdiutil create -volname "$PRODUCT_NAME" -srcfolder "$OUTPUT_DIR/dmg-root" -ov -format UDZO "$DMG_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"
shasum -a 256 "$DMG_PATH" "$ZIP_PATH" > "$OUTPUT_DIR/SHA256SUMS-$ARCH_LABEL.txt"
rm -rf "$OUTPUT_DIR/dmg-root"

echo "macOS 构建完成：$DMG_PATH"
echo "备用 ZIP：$ZIP_PATH"
