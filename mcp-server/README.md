# Browser Proxy MCP Server

A minimal, stateless MCP server that acts as a thin proxy between MCP clients and Chrome.

## Philosophy

- **The browser IS the session** - no internal state tracking
- **Always works with the active tab** - queries real browser state before each operation
- **Minimal tool set** - just 3 essential tools instead of 17+
- **Stateful browser, stateless MCP** - persistent cookies/storage in browser, no MCP session

## Key Features

### Real-time State Synchronization
- Always checks which tab is ACTUALLY active before operations
- No stale state - queries browser every time
- Works correctly even when user manually switches tabs

### Essential Tools Only

1. **browser_action** - Execute actions on active tab
   - navigate, evaluate, screenshot, get_content, click, fill, wait
   
2. **browser_tabs** - List all tabs or switch tabs
   - Shows which tab is actually focused (👁 marker)
   
3. **browser_info** - Get current browser state

## Architecture Benefits

### vs JavaScript Playwright MCP
- ✅ No state synchronization bugs
- ✅ Works with manual tab switches
- ✅ Minimal code surface
- ✅ Easy to extend

### vs Stateless Python Servers
- ✅ Persistent browser session (cookies, localStorage)
- ✅ Faster (no browser startup cost)
- ✅ Can work with existing tabs

## Usage

### In Docker Container

The server connects to Chrome at `http://localhost:9222` by default:

```bash
# Option 1: Use with existing Node.js MCP (replace it)
docker exec -it playwright-browser /mcp-server/start_server.sh

# Option 2: Run directly
docker exec -it playwright-browser python /mcp-server/browser_proxy.py
```

### Standalone

```bash
# Install dependencies
pip install -r requirements.txt

# Start Chrome with debugging
google-chrome --remote-debugging-port=9222

# Run server
CDP_ENDPOINT=http://localhost:9222 python browser_proxy.py
```

## Migration Path

This server is designed to easily accommodate tools from the existing Python MCP servers:

- **html_extractor_server.py** tools can be added as new actions in `browser_action`
- **screen_server.py** screenshot functionality already included, AI analysis can be added
- Modular design allows easy extension without breaking core proxy functionality

## Configuration

Environment variables:
- `CDP_ENDPOINT` - Chrome DevTools Protocol endpoint (default: `http://localhost:9222`)

## Technical Details

- Uses Playwright's CDP connection for reliability
- Async Python for performance
- No internal state - always queries browser
- Graceful error handling
- Comprehensive logging