# Playwright Browser Container

A Docker container that provides a browser environment with Playwright MCP server, accessible via VNC and HTTP/SSE.

## Features

- 🖥️ Virtual display (Xvfb) with configurable resolution
- 🌐 Chrome/Chromium browser with persistent profile
- 🔧 Playwright MCP server accessible via HTTP/SSE
- 👁️ VNC access through noVNC web interface
- 📦 All-in-one containerized solution

## Quick Start

### Build and Run

```bash
# Build the container
docker-compose build

# Start the container
docker-compose up -d

# View logs
docker-compose logs -f
```

### Access Points

- **VNC Web Interface**: http://localhost:6080/browser-viewer.html
- **Playwright MCP Endpoint**: http://localhost:8931
- **Chrome DevTools**: http://localhost:9222 (optional, for debugging)

## Configuration

### Environment Variables

- `DISPLAY`: Display number (default: `:99`)
- `RESOLUTION`: Screen resolution (default: `1920x1080`)

### Volumes

- `browser-data`: Persistent browser profile and data
- `chrome-downloads`: Downloads directory

## Claude Code Integration

Update your Claude Code configuration to use the HTTP endpoint:

```json
{
  "mcpServers": {
    "playwright": {
      "type": "sse",
      "url": "http://localhost:8931"
    }
  }
}
```

Or in `.claude.json`:

```json
"playwright": {
  "type": "http",
  "url": "http://localhost:8931/mcp"
}
```

## Architecture

The container runs multiple services managed by supervisor:

1. **Xvfb**: Virtual framebuffer X server
2. **x11vnc**: VNC server for remote display access
3. **websockify**: WebSocket to TCP proxy for noVNC
4. **Playwright MCP**: MCP server for browser automation
5. **Chrome**: Browser instance (optional, for idle state)

## Development

### Building Locally

```bash
docker build -t playwright-browser .
```

### Running Without Compose

```bash
docker run -d \
  -p 6080:6080 \
  -p 8931:8931 \
  -e RESOLUTION=1920x1080 \
  --name playwright-browser \
  playwright-browser
```

## Troubleshooting

### Check Service Status

```bash
docker exec playwright-browser supervisorctl status
```

### View Logs

```bash
# All logs
docker-compose logs

# Specific service logs
docker exec playwright-browser tail -f /var/log/supervisor/playwright-mcp.log
```

### Test MCP Connection

```bash
curl http://localhost:8931/health
```

## License

MIT