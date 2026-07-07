# Playwright Browser Container

Containerized browser automation environment with Chrome, Playwright MCP, persistent browser profiles, VNC/noVNC access, and HTTP/SSE connectivity.

This project isolates browser automation into a reproducible container so agent workflows can use a real browser without depending on a developer's local desktop state.

## Why I Built It

Browser automation is useful for AI workflows, but local browser state is messy. Profiles, cookies, display state, downloads, and browser versions can all affect behavior. For long-running agent workflows, the browser should be a controlled service boundary, not an implicit dependency on someone's machine.

A second motivation was tool-surface control. General-purpose browser MCP servers expose many browser actions because they need to cover every common interaction. That flexibility is useful, but for coding agents it can be expensive: every loaded tool schema and every verbose accessibility snapshot consumes context and increases the chance that the model chooses the wrong tool.

This project is intentionally narrower. The goal is a containerized browser service with persistent state, visual handoff, and a smaller operational interface for the workflows I actually needed.

The design is based on a simple premise: for agent workflows, fewer high-signal tools are often better than a broad low-level browser API.

## Design Rationale: Smaller Tool Surface

This project is not a replacement for Playwright. It is an opinionated browser runtime for agent workflows.

The official Playwright MCP server is broad by design. It exposes tools for navigation, clicking, typing, screenshots, keyboard and mouse input, dialogs, tabs, network inspection, storage state, and arbitrary Playwright code execution. That is useful for general automation, but it also creates a large decision surface for an LLM.

The narrower design here is motivated by three observations:

- OpenAI recommends keeping the number of initially available functions small for higher accuracy and suggests fewer than 20 functions at the start of a turn.
- Anthropic notes that too many or overlapping tools can distract agents and increase tool-use mistakes.
- Microsoft's own Playwright MCP README says coding agents may benefit from CLI plus skills because they avoid loading large tool schemas and verbose accessibility trees into model context.

In practice, this means the browser layer should expose the smallest set of operations needed for the task, keep persistent session state outside the model, and allow visual human takeover when the agent hits authentication, CAPTCHAs, or ambiguous UI states.

## Key Technical Points

- Chrome/Chromium inside a Docker container
- Playwright MCP server exposed over HTTP/SSE
- Virtual display through Xvfb
- VNC/noVNC access for visual inspection
- Persistent browser profile volume
- Downloads volume
- Supervisor-managed services
- Optional Chrome DevTools port

## Architecture

```text
playwright-browser-container/
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── supervisord.conf
│   ├── chrome-preferences.json
│   └── browser-viewer.html
├── mcp-server/
└── scripts/
```

Runtime services:

1. `Xvfb` - virtual display
2. `x11vnc` - VNC server
3. `websockify` - WebSocket bridge for noVNC
4. `Playwright MCP` - browser automation interface
5. `Chrome` - browser instance with persistent profile

## Quick Start

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

Access points:

```text
VNC web UI:        http://localhost:6080/browser-viewer.html
Playwright MCP:   http://localhost:8931
Chrome DevTools:  http://localhost:9222
```

## Claude/Codex MCP Configuration

Example MCP configuration:

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

Some clients expect the `/mcp` path:

```json
{
  "mcpServers": {
    "playwright": {
      "type": "http",
      "url": "http://localhost:8931/mcp"
    }
  }
}
```

## Run Without Compose

```bash
docker build -t playwright-browser .

docker run -d \
  -p 6080:6080 \
  -p 8931:8931 \
  -e RESOLUTION=1920x1080 \
  --name playwright-browser \
  playwright-browser
```

## Troubleshooting

Check service status:

```bash
docker exec playwright-browser supervisorctl status
```

View logs:

```bash
docker compose logs
docker exec playwright-browser tail -f /var/log/supervisor/playwright-mcp.log
```

Test MCP health:

```bash
curl http://localhost:8931/health
```

## Status

Infrastructure prototype for browser-backed agent workflows. Intended for local and controlled environments, not as an exposed public browser service.

Security note: do not expose this container on an untrusted network. Browser automation infrastructure can hold cookies, account sessions, downloads, and privileged execution paths.

## References

- [OpenAI function calling best practices](https://developers.openai.com/api/docs/guides/function-calling)
- [Anthropic: Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Microsoft Playwright MCP README](https://github.com/microsoft/playwright-mcp)
- [Playwright MCP documentation](https://playwright.dev/docs/getting-started-mcp)
