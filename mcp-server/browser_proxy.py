#!/usr/bin/env python3
"""
Minimal Browser Proxy MCP Server

A thin proxy between MCP clients and the actual Chrome browser.
No session tracking - the browser IS the session.
Always works with the actual active tab.
"""

import os
import json
import logging
import asyncio
from typing import Any, Optional, Sequence
from datetime import datetime

from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import Tool, TextContent
from playwright.async_api import async_playwright, Page, Browser

class BrowserProxy:
    """Thin proxy to actual browser state - no internal tracking"""
    
    def __init__(self, cdp_endpoint: str = "http://localhost:9222"):
        self.app = Server("browser-proxy")
        self.cdp_endpoint = cdp_endpoint
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("browser-proxy")
        
        # Playwright connection (reused but stateless)
        self.playwright = None
        self.browser: Optional[Browser] = None
        
        self.setup_handlers()
    
    async def get_browser(self) -> Browser:
        """Get or create browser connection"""
        if not self.browser:
            if not self.playwright:
                self.playwright = await async_playwright().start()
            
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_endpoint)
                self.logger.info(f"Connected to browser at {self.cdp_endpoint}")
            except Exception as e:
                self.logger.error(f"Failed to connect to CDP: {e}")
                raise RuntimeError(f"Cannot connect to browser at {self.cdp_endpoint}")
        
        return self.browser
    
    async def get_active_page(self) -> Page:
        """
        Get the ACTUALLY active page/tab right now.
        No tracking, just ask the browser what's focused.
        """
        browser = await self.get_browser()
        
        # Get all pages from all contexts
        all_pages = []
        for context in browser.contexts:
            all_pages.extend(context.pages)
        
        if not all_pages:
            raise RuntimeError("No pages open in browser")
        
        # Find which page actually has focus RIGHT NOW
        for page in all_pages:
            try:
                # Check if this page is focused and visible
                is_active = await page.evaluate("""() => {
                    return document.hasFocus() && document.visibilityState === 'visible';
                }""")
                
                if is_active:
                    self.logger.debug(f"Active page: {page.url}")
                    return page
                    
            except Exception:
                # Page might be navigating or closed
                continue
        
        # No page has focus? Just use the first one
        self.logger.warning("No page has focus, using first available")
        return all_pages[0]
    
    async def list_all_tabs(self) -> list:
        """Get current state of ALL tabs"""
        browser = await self.get_browser()
        tabs = []
        tab_index = 0
        
        for context in browser.contexts:
            for page in context.pages:
                try:
                    # Get real-time info from each tab
                    info = await page.evaluate("""() => ({
                        title: document.title,
                        url: window.location.href,
                        hasFocus: document.hasFocus(),
                        visible: document.visibilityState === 'visible',
                        domain: window.location.hostname
                    })""")
                    
                    tabs.append({
                        "index": tab_index,
                        "title": info.get("title", "Untitled"),
                        "url": info.get("url", page.url),
                        "active": info.get("hasFocus", False) and info.get("visible", False),
                        "domain": info.get("domain", "")
                    })
                    
                except Exception as e:
                    # Tab might be loading
                    tabs.append({
                        "index": tab_index,
                        "title": "(Loading...)",
                        "url": page.url,
                        "active": False,
                        "domain": ""
                    })
                
                tab_index += 1
        
        return tabs
    
    async def switch_to_tab(self, index: int) -> dict:
        """Switch to a specific tab by index"""
        browser = await self.get_browser()
        all_pages = []
        
        for context in browser.contexts:
            all_pages.extend(context.pages)
        
        if index < 0 or index >= len(all_pages):
            raise ValueError(f"Tab index {index} out of range (0-{len(all_pages)-1})")
        
        page = all_pages[index]
        await page.bring_to_front()
        
        # Return info about the tab we switched to
        try:
            info = await page.evaluate("""() => ({
                title: document.title,
                url: window.location.href
            })""")
            return info
        except:
            return {"title": "Unknown", "url": page.url}
    
    async def execute_on_active_tab(self, action: str, **kwargs) -> Any:
        """
        Execute an action on whatever tab is currently active.
        This is the core principle - always work with what's actually active.
        """
        page = await self.get_active_page()
        
        if action == "navigate":
            url = kwargs.get("url")
            if not url:
                raise ValueError("URL required for navigate")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {"navigated_to": url}
            
        elif action == "evaluate":
            expression = kwargs.get("expression")
            if not expression:
                raise ValueError("Expression required for evaluate")
            result = await page.evaluate(expression)
            return result
            
        elif action == "screenshot":
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = kwargs.get("path", f"screenshot_{timestamp}.png")
            full_page = kwargs.get("full_page", False)
            
            screenshot_data = await page.screenshot(full_page=full_page)
            
            # Save to file
            with open(path, "wb") as f:
                f.write(screenshot_data)
            
            return {"screenshot_saved": path, "size": len(screenshot_data)}
            
        elif action == "get_content":
            # Get the page's text content
            content = await page.evaluate("""() => {
                return document.body ? document.body.innerText : '';
            }""")
            return {"content": content[:5000]}  # Limit to first 5000 chars
            
        elif action == "click":
            selector = kwargs.get("selector")
            if not selector:
                raise ValueError("Selector required for click")
            
            # Try to click, with error handling
            try:
                await page.click(selector, timeout=5000)
                return {"clicked": selector}
            except Exception as e:
                # Element might not exist
                return {"error": f"Could not click {selector}: {str(e)}"}
                
        elif action == "fill":
            selector = kwargs.get("selector")
            value = kwargs.get("value")
            if not selector or value is None:
                raise ValueError("Selector and value required for fill")
            
            await page.fill(selector, value)
            return {"filled": selector, "value": value}
            
        elif action == "wait":
            timeout = kwargs.get("timeout", 3000)
            await page.wait_for_timeout(timeout)
            return {"waited": f"{timeout}ms"}
            
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def setup_handlers(self):
        @self.app.list_tools()
        async def list_tools() -> list[Tool]:
            """Only essential tools - no bloat"""
            return [
                Tool(
                    name="browser_action",
                    description="""Execute action on the CURRENTLY ACTIVE tab.
                    
Actions:
- navigate: Go to a URL
- evaluate: Run JavaScript and return result  
- screenshot: Capture the page
- get_content: Get page text content
- click: Click an element
- fill: Fill a form field
- wait: Wait for timeout

Always operates on whatever tab the user is actually looking at.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["navigate", "evaluate", "screenshot", "get_content", "click", "fill", "wait"],
                                "description": "Action to perform"
                            },
                            "url": {"type": "string", "description": "URL for navigate"},
                            "expression": {"type": "string", "description": "JavaScript for evaluate"},
                            "selector": {"type": "string", "description": "CSS selector for click/fill"},
                            "value": {"type": "string", "description": "Value for fill"},
                            "full_page": {"type": "boolean", "description": "Full page screenshot", "default": False},
                            "timeout": {"type": "integer", "description": "Timeout in ms for wait", "default": 3000}
                        },
                        "required": ["action"]
                    }
                ),
                Tool(
                    name="browser_tabs",
                    description="List all tabs or switch to a specific tab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["list", "switch"],
                                "description": "list: show all tabs, switch: change active tab"
                            },
                            "index": {
                                "type": "integer",
                                "description": "Tab index for switch action"
                            }
                        },
                        "required": ["action"]
                    }
                ),
                Tool(
                    name="browser_info",
                    description="Get current browser state and active tab info",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.app.call_tool()
        async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
            try:
                if name == "browser_action":
                    action = arguments.get("action")
                    if not action:
                        return [TextContent(type="text", text="ERROR: action is required")]
                    
                    # Remove 'action' from arguments before passing as kwargs
                    kwargs = {k: v for k, v in arguments.items() if k != "action"}
                    
                    # Execute on whatever tab is active RIGHT NOW
                    result = await self.execute_on_active_tab(action, **kwargs)
                    
                    # Format result nicely
                    if action == "navigate":
                        return [TextContent(type="text", text=f"✓ Navigated to {result['navigated_to']}")]
                    elif action == "screenshot":
                        return [TextContent(type="text", text=f"✓ Screenshot saved: {result['screenshot_saved']}")]
                    elif action == "get_content":
                        content = result.get("content", "")
                        return [TextContent(type="text", text=f"Page content:\n{content}")]
                    else:
                        return [TextContent(type="text", text=json.dumps(result, indent=2))]
                
                elif name == "browser_tabs":
                    action = arguments.get("action", "list")
                    
                    if action == "list":
                        tabs = await self.list_all_tabs()
                        
                        # Format nicely
                        lines = ["### Browser Tabs"]
                        for tab in tabs:
                            active = "👁 " if tab["active"] else "  "
                            lines.append(f"{active}{tab['index']}: [{tab['domain']}] {tab['title']}")
                        
                        return [TextContent(type="text", text="\n".join(lines))]
                    
                    elif action == "switch":
                        index = arguments.get("index")
                        if index is None:
                            return [TextContent(type="text", text="ERROR: index required for switch")]
                        
                        info = await self.switch_to_tab(index)
                        return [TextContent(type="text", text=f"✓ Switched to tab {index}: {info.get('title', 'Unknown')}")]
                    
                elif name == "browser_info":
                    # Get active page info
                    page = await self.get_active_page()
                    
                    info = await page.evaluate("""() => ({
                        title: document.title,
                        url: window.location.href,
                        domain: window.location.hostname,
                        readyState: document.readyState,
                        hasFocus: document.hasFocus(),
                        visible: document.visibilityState,
                        cookiesEnabled: navigator.cookieEnabled,
                        localStorage: typeof(Storage) !== "undefined",
                        viewport: {
                            width: window.innerWidth,
                            height: window.innerHeight
                        }
                    })""")
                    
                    # Get tab count
                    tabs = await self.list_all_tabs()
                    info["total_tabs"] = len(tabs)
                    info["cdp_endpoint"] = self.cdp_endpoint
                    
                    return [TextContent(type="text", text=json.dumps(info, indent=2))]
                
                else:
                    return [TextContent(type="text", text=f"ERROR: Unknown tool: {name}")]
                    
            except Exception as e:
                self.logger.error(f"Tool error: {str(e)}", exc_info=True)
                return [TextContent(type="text", text=f"ERROR: {str(e)}")]
    
    async def cleanup(self):
        """Clean up connections"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def run(self):
        """Start the MCP server"""
        from starlette.applications import Starlette
        import uvicorn
        
        self.logger.info("🚀 Browser Proxy MCP Server")
        self.logger.info(f"📡 Connecting to Chrome at {self.cdp_endpoint}")
        self.logger.info("✨ No session tracking - browser IS the session")
        self.logger.info("🌐 Starting HTTP/SSE server on port 8931")
        
        # Create the HTTP transport
        transport = StreamableHTTPServerTransport(
            mcp_session_id=None,  # No session tracking
            is_json_response_enabled=False  # Use SSE
        )
        
        # Create Starlette app
        starlette_app = Starlette()
        # handle_request is an ASGI app, not a regular route handler
        starlette_app.mount("/mcp", transport.handle_request)
        
        # Run the server with transport
        async with transport.connect() as (read_stream, write_stream):
            # Start MCP server in background
            server_task = asyncio.create_task(
                self.app.run(
                    read_stream,
                    write_stream,
                    self.app.create_initialization_options()
                )
            )
            
            # Start uvicorn server
            config = uvicorn.Config(
                app=starlette_app,
                host="0.0.0.0",
                port=8931,
                log_level="info"
            )
            server = uvicorn.Server(config)
            
            try:
                await server.serve()
            finally:
                server_task.cancel()
                await self.cleanup()

async def main():
    # Get CDP endpoint from environment or use default
    cdp_endpoint = os.getenv("CDP_ENDPOINT", "http://localhost:9222")
    
    server = BrowserProxy(cdp_endpoint)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())