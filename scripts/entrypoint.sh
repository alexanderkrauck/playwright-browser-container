#!/bin/bash

set -e

echo "Starting Playwright Browser Container..."

# Set display resolution if provided
if [ ! -z "$RESOLUTION" ]; then
    echo "Setting resolution to: $RESOLUTION"
    export RESOLUTION="$RESOLUTION"
else
    export RESOLUTION="1920x1080"
fi

# Create necessary directories
mkdir -p /var/log/supervisor
mkdir -p /data/chrome-profile
mkdir -p /root/Downloads
mkdir -p /root/.playwright-browser-data

# Clean up stale Chrome lock files from previous runs
echo "Cleaning up stale Chrome lock files..."
rm -f /data/chrome-profile/Singleton*
rm -rf /tmp/.com.google.Chrome.*

# Set proper permissions
chmod -R 755 /var/log/supervisor
chmod -R 755 /data

# Check if noVNC files exist
if [ ! -f /usr/share/novnc/vnc.html ]; then
    echo "Installing noVNC files..."
    cp -r /usr/share/novnc/* /usr/share/novnc/ 2>/dev/null || true
fi

# Ensure browser-viewer.html is in place
if [ -f /config/browser-viewer.html ]; then
    cp /config/browser-viewer.html /usr/share/novnc/browser-viewer.html
fi

# Wait for display to be ready
echo "Waiting for display to be ready..."
timeout 10 bash -c 'until xdpyinfo -display :99 >/dev/null 2>&1; do sleep 0.5; done' || true

# Start supervisor
echo "Starting supervisor..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf