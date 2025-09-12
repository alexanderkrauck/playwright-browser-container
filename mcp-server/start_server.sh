#!/bin/bash
# Start the Python MCP browser proxy server

set -e

echo "Starting Browser Proxy MCP Server..."

# Ensure Chrome is running and get CDP endpoint
if ! curl -s http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "ERROR: Chrome is not running on port 9222"
    echo "Please ensure Chrome is started with --remote-debugging-port=9222"
    exit 1
fi

# Set CDP endpoint
export CDP_ENDPOINT=${CDP_ENDPOINT:-"http://localhost:9222"}

echo "Connecting to Chrome at: $CDP_ENDPOINT"

# Install dependencies if needed
if [ ! -d "/root/.local/lib/python3.*/site-packages/mcp" ]; then
    echo "Installing Python dependencies..."
    pip install --user -r /mcp-server/requirements.txt
    
    # Install playwright browsers if needed
    python -m playwright install chromium
fi

# Start the MCP server
exec python /mcp-server/browser_proxy.py