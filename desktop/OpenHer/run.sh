#!/bin/bash
# Build and run OpenHer as a proper .app bundle with icon
set -e

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$PROJ_DIR/.build/debug"
APP_DIR="$BUILD_DIR/OpenHer.app"
CONTENTS="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"

# Build
echo "🔨 Building..."
cd "$PROJ_DIR"
swift build 2>&1

# Kill existing instance
pkill -f "OpenHer.app/Contents/MacOS/OpenHer" 2>/dev/null || true
pkill -f ".build/debug/OpenHer" 2>/dev/null || true
sleep 0.5

# Create .app bundle structure
rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

# Copy binary
cp "$BUILD_DIR/OpenHer" "$MACOS_DIR/OpenHer"

# Copy icon
if [ -f "$PROJ_DIR/Sources/Resources/AppIcon.icns" ]; then
    cp "$PROJ_DIR/Sources/Resources/AppIcon.icns" "$RESOURCES_DIR/AppIcon.icns"
fi

# Create Info.plist
cat > "$CONTENTS/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>OpenHer</string>
    <key>CFBundleIdentifier</key>
    <string>com.openher.app</string>
    <key>CFBundleName</key>
    <string>OpenHer</string>
    <key>CFBundleDisplayName</key>
    <string>OpenHer</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Copy SPM resources bundle if exists
for bundle in "$BUILD_DIR"/*.bundle; do
    if [ -d "$bundle" ]; then
        cp -R "$bundle" "$MACOS_DIR/"
    fi
done

echo "🚀 Launching OpenHer..."
open "$APP_DIR"
