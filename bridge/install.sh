#!/bin/bash

# Graphic Density — Native Messaging Host Installer
# Registers the bridge server with Chrome so the extension can launch it.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST_NAME="com.graphicdensity.bridge"
SERVER_PATH="$SCRIPT_DIR/server.js"

# Detect OS
case "$(uname -s)" in
  Darwin*)
    MANIFEST_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
    ;;
  Linux*)
    MANIFEST_DIR="$HOME/.config/google-chrome/NativeMessagingHosts"
    ;;
  *)
    echo "Unsupported OS. For Windows, run install.bat instead."
    exit 1
    ;;
esac

# Get the extension ID — user needs to provide it after loading unpacked
EXTENSION_ID="${1:-}"

if [ -z "$EXTENSION_ID" ]; then
  echo ""
  echo "  Graphic Density — Native Messaging Setup"
  echo "  ─────────────────────────────────────────"
  echo ""
  echo "  Usage: ./install.sh <extension-id>"
  echo ""
  echo "  To find your extension ID:"
  echo "  1. Go to chrome://extensions/"
  echo "  2. Find 'Graphic Density - Browser Execution Layer'"
  echo "  3. Copy the ID (long string of letters)"
  echo ""
  echo "  Example: ./install.sh abcdefghijklmnopqrstuvwxyz123456"
  echo ""
  exit 1
fi

# Make server executable
chmod +x "$SERVER_PATH"

# Create manifest directory
mkdir -p "$MANIFEST_DIR"

# Write native messaging manifest
MANIFEST_PATH="$MANIFEST_DIR/$HOST_NAME.json"

cat > "$MANIFEST_PATH" << EOF
{
  "name": "$HOST_NAME",
  "description": "Graphic Density API Bridge",
  "path": "$SERVER_PATH",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$EXTENSION_ID/"
  ]
}
EOF

echo ""
echo "  ✓ Native messaging host registered"
echo ""
echo "  Manifest: $MANIFEST_PATH"
echo "  Server:   $SERVER_PATH"
echo "  Extension: $EXTENSION_ID"
echo ""
echo "  Next steps:"
echo "  1. Reload the extension in chrome://extensions/"
echo "  2. The bridge will start automatically"
echo "  3. Test: curl http://127.0.0.1:7080/health"
echo ""
