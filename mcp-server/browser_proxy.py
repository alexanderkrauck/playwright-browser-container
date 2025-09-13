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
import re
from typing import Any, Optional, Sequence, List, Dict
from datetime import datetime
from difflib import SequenceMatcher

from mcp.server import Server
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import Tool, TextContent, ImageContent
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
    
    async def smart_click(self, page: Page, target: str) -> Dict:
        """Click by text or CSS selector using trusted mouse events with auto-scrolling"""
        # CSS selector detection
        if target.startswith(('#', '.', '[')) or ' > ' in target or target.startswith('div[') or target.startswith('button['):
            try:
                await page.click(target, timeout=5000)
                return {"clicked": target, "method": "css_selector"}
            except Exception as e:
                return {"error": f"Could not click {target}: {str(e)}"}

        # Text-based clicking with trusted mouse events and auto-scrolling
        try:
            # Enhanced search with viewport checking and auto-scroll
            result = await page.evaluate(f"""
                (targetText) => {{
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    let bestMatch = null;

                    while (node = walker.nextNode()) {{
                        const text = node.textContent.trim();
                        if (text === targetText || text.includes(targetText)) {{
                            const element = node.parentElement;
                            if (!element) continue;

                            const range = document.createRange();
                            range.selectNodeContents(node);
                            const rect = range.getBoundingClientRect();

                            if (rect.width > 0 && rect.height > 0) {{
                                // Check if element is in viewport
                                const isVisible = rect.top >= 0 &&
                                                rect.left >= 0 &&
                                                rect.bottom <= window.innerHeight &&
                                                rect.right <= window.innerWidth;

                                const match = {{
                                    x: rect.left + rect.width / 2,
                                    y: rect.top + rect.height / 2,
                                    element: element,
                                    visible: isVisible,
                                    found: true
                                }};

                                // If visible, use immediately
                                if (isVisible) {{
                                    return match;
                                }}

                                // Otherwise, store as potential match
                                if (!bestMatch) {{
                                    bestMatch = match;
                                }}
                            }}
                        }}
                    }}

                    return bestMatch || {{ found: false }};
                }}
            """, target)

            if result.get('found'):
                # If element is visible, click directly
                if result.get('visible'):
                    await page.mouse.click(result['x'], result['y'])
                    return {"clicked": target, "method": "trusted_mouse_click", "coordinates": {"x": result['x'], "y": result['y']}}

                # If not visible, scroll into view first
                else:
                    scroll_result = await page.evaluate(f"""
                        (targetText) => {{
                            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                            let node;

                            while (node = walker.nextNode()) {{
                                const text = node.textContent.trim();
                                if (text === targetText || text.includes(targetText)) {{
                                    const element = node.parentElement;
                                    if (element) {{
                                        // Scroll element into view
                                        element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                        return {{ scrolled: true }};
                                    }}
                                }}
                            }}
                            return {{ scrolled: false }};
                        }}
                    """, target)

                    if scroll_result.get('scrolled'):
                        # Wait for scroll animation to complete
                        await page.wait_for_timeout(500)

                        # Now get new coordinates after scrolling
                        new_result = await page.evaluate(f"""
                            (targetText) => {{
                                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                                let node;

                                while (node = walker.nextNode()) {{
                                    const text = node.textContent.trim();
                                    if (text === targetText || text.includes(targetText)) {{
                                        const range = document.createRange();
                                        range.selectNodeContents(node);
                                        const rect = range.getBoundingClientRect();

                                        if (rect.width > 0 && rect.height > 0) {{
                                            return {{
                                                x: rect.left + rect.width / 2,
                                                y: rect.top + rect.height / 2,
                                                found: true
                                            }};
                                        }}
                                    }}
                                }}
                                return {{ found: false }};
                            }}
                        """, target)

                        if new_result.get('found'):
                            await page.mouse.click(new_result['x'], new_result['y'])
                            return {"clicked": target, "method": "scroll_then_click", "coordinates": {"x": new_result['x'], "y": new_result['y']}}

            return {"error": f"Could not find text: '{target}'"}

        except Exception as e:
            return {"error": f"Click failed: {str(e)}"}

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

            # Custom wait conditions and timeout
            wait_until = kwargs.get("wait_until", "domcontentloaded")
            timeout = kwargs.get("timeout", 30000)

            # Validate wait_until parameter
            valid_wait_conditions = ["load", "domcontentloaded", "networkidle", "commit"]
            if wait_until not in valid_wait_conditions:
                raise ValueError(f"Invalid wait_until: {wait_until}. Must be one of: {valid_wait_conditions}")

            await page.goto(url, wait_until=wait_until, timeout=timeout)
            return {"navigated_to": url, "wait_until": wait_until, "timeout": timeout}
            
        elif action == "evaluate":
            expression = kwargs.get("expression")
            if not expression:
                raise ValueError("Expression required for evaluate")
            result = await page.evaluate(expression)
            return result
            
        elif action == "screenshot":
            import base64
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = kwargs.get("path", f"screenshot_{timestamp}.png")
            full_page = kwargs.get("full_page", False)
            
            screenshot_data = await page.screenshot(full_page=full_page)
            
            # Convert to base64 for ImageContent
            base64_data = base64.b64encode(screenshot_data).decode('utf-8')
            
            # Also save to file for reference
            with open(path, "wb") as f:
                f.write(screenshot_data)
            
            return {"base64": base64_data, "path": path, "size": len(screenshot_data)}
            
        elif action == "get_content":
            # Get the page's text content
            content = await page.evaluate("""() => {
                return document.body ? document.body.innerText : '';
            }""")
            return {"content": content[:5000]}  # Limit to first 5000 chars
            
        elif action == "click":
            target = kwargs.get("target") or kwargs.get("selector")  # Support both for compatibility
            if not target:
                raise ValueError("Target text or selector required for click")

            return await self.smart_click(page, target)
                
        elif action == "fill":
            selector = kwargs.get("selector")
            value = kwargs.get("value")
            if not selector or value is None:
                raise ValueError("Selector and value required for fill")

            await page.fill(selector, value)
            return {"filled": selector, "value": value}

        elif action == "playwright":
            script = kwargs.get("script")
            if not script:
                raise ValueError("Playwright script required")

            # Execute Playwright script with page context
            try:
                # This tool is exclusively for Playwright Python API calls
                if "await page." not in script:
                    raise ValueError("This tool is for Playwright API commands only. Use 'await page.*' syntax. For JavaScript execution, use browser_evaluate instead.")

                # Execute as Python Playwright API calls
                namespace = {'page': page}
                exec_code = f"""
async def _exec_playwright():
{chr(10).join('    ' + line if line.strip() else '' for line in script.strip().split(chr(10)))}
"""
                exec(exec_code, namespace)
                result = await namespace['_exec_playwright']()

                return {"result": result, "executed": True}
            except Exception as e:
                return {"error": f"Playwright script failed: {str(e)}"}
            
            
        else:
            raise ValueError(f"Unknown action: {action}")
    
    def setup_handlers(self):
        @self.app.list_tools()
        async def list_tools() -> list[Tool]:
            """Individual browser tools for better organization"""
            return [
                Tool(
                    name="browser_navigate",
                    description="Navigate to a URL on the currently active tab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL to navigate to"},
                            "wait_until": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle", "commit"], "description": "When to consider navigation complete (default: domcontentloaded)"},
                            "timeout": {"type": "integer", "description": "Navigation timeout in milliseconds (default: 30000)"}
                        },
                        "required": ["url"]
                    }
                ),
                Tool(
                    name="browser_evaluate",
                    description="Execute JavaScript code in the browser context. For running any JavaScript: simple expressions ('document.title'), complex async functions ('(async () => { await fetch(...); return data; })()'), DOM manipulation, or multi-line scripts. This is your go-to tool for JavaScript execution.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string", "description": "JavaScript code to execute. Can be simple expressions or complex async IIFEs. Examples: 'document.title' or '(async () => { const result = await fetch(...); return result; })()'"}
                        },
                        "required": ["expression"]
                    }
                ),
                Tool(
                    name="browser_screenshot",
                    description="Take a screenshot of the currently active tab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "full_page": {"type": "boolean", "description": "Capture full page or just viewport (default: false)"}
                        }
                    }
                ),
                Tool(
                    name="browser_get_content",
                    description="Get basic page text content (document.body.innerText, limited to 5000 chars)",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="browser_click",
                    description="Click an element by text content or CSS selector using trusted mouse events",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "Text to click or CSS selector"}
                        },
                        "required": ["target"]
                    }
                ),
                Tool(
                    name="browser_fill",
                    description="Fill a form field on the currently active tab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string", "description": "CSS selector for the input field"},
                            "value": {"type": "string", "description": "Value to fill"}
                        },
                        "required": ["selector", "value"]
                    }
                ),
                Tool(
                    name="browser_playwright",
                    description="Execute Playwright Python API commands directly. This is exclusively for automation tasks that need Playwright's API like 'await page.mouse.wheel(0, 300)', 'await page.wait_for_timeout(500)', 'await page.keyboard.press(\"Enter\")', 'await page.hover(\"#element\")'. For JavaScript execution, use browser_evaluate instead.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "script": {"type": "string", "description": "Playwright Python API commands. Must use 'await page.*' for browser automation (mouse, keyboard, waits, etc). Variables need '=' assignment. Returns must use 'return' statement. For pure JavaScript, use browser_evaluate."}
                        },
                        "required": ["script"]
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
        async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent]:
            try:
                # Individual browser tools
                if name == "browser_navigate":
                    result = await self.execute_on_active_tab("navigate", **arguments)
                    return [TextContent(type="text", text=f"✓ Navigated to {result['navigated_to']}")]

                elif name == "browser_evaluate":
                    result = await self.execute_on_active_tab("evaluate", **arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]

                elif name == "browser_screenshot":
                    result = await self.execute_on_active_tab("screenshot", **arguments)
                    return [ImageContent(
                        type="image",
                        data=result["base64"],
                        mimeType="image/png"
                    )]

                elif name == "browser_get_content":
                    result = await self.execute_on_active_tab("get_content", **arguments)
                    content = result.get("content", "")
                    return [TextContent(type="text", text=f"Page content:\n{content}")]

                elif name == "browser_click":
                    result = await self.execute_on_active_tab("click", **arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]

                elif name == "browser_fill":
                    result = await self.execute_on_active_tab("fill", **arguments)
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]

                elif name == "browser_playwright":
                    result = await self.execute_on_active_tab("playwright", **arguments)
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