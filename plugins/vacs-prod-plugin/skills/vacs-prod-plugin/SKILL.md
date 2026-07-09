---
name: vacs-prod-plugin
description: Connect to and use the VACS project MCP server from Codex. Use when Codex needs to call VACS MCP tools, inspect or mutate the OAuth-bound current project, read VACS MCP API documentation, or route project story, premise, chapter, export, and file operations through the configured MCP endpoint.
---

# VACS Prod Plugin

## Overview

Use this skill with the `vacs-prod-plugin` MCP server. The plugin points to the configured endpoint:

- MCP URL: `https://vacs.jgcat.net/mcp`
- OAuth resource: `https://vacs.jgcat.net/`
- OAuth authorize page: `https://vacs.jgcat.net/oauth/mcp/authorize`
- OAuth token endpoint: `https://vacs.jgcat.net/oauth/mcp/token`

During OAuth authorization, VACS asks the logged-in user to choose one project. The resulting bearer token is bound to that user and project. All tool calls operate only on that current project; do not pass or invent `project_id` in tool arguments.

## Tools

The server exposes two tools.

`read_api_doc`

Read an allowed Markdown document under `/api/mcp/docs/...`.

Arguments:

- `path`: full docs path, for example `/api/mcp/docs/overview.md` or `/api/mcp/docs/current-project/chapters.md`.

Use `read_api_doc` before calling an unfamiliar API route. Start with `/api/mcp/docs/overview.md`, then open the route-specific document named in the overview.

`request_api`

Call a registered `/api/mcp/current-project/...` API route through the OAuth-bound project session.

Arguments:

- `url`: relative API path such as `/api/mcp/current-project/overview`.
- `method`: HTTP method, for example `GET`, `POST`, `PATCH`, or `DELETE`.
- `request_body`: optional JSON object for non-GET requests.
- `response_filter`: required jq-like projection beginning with `.data`.

Prefer narrow `response_filter` values. For list calls, ask for only identifiers and status fields first, then fetch details with a second call when needed.

## Usage Pattern

1. Confirm the `vacs-prod-plugin` MCP server is available.
2. If authentication is required, start MCP login and complete OAuth at `https://vacs.jgcat.net/`.
3. Call `read_api_doc` with `/api/mcp/docs/overview.md`.
4. Choose the route-specific doc from the overview and read it before writes or multi-step operations.
5. Call `request_api` with an allowed `/api/mcp/current-project/...` path and a precise `response_filter`.

## API Reference

The copied overview from the VACS repository is available at `references/overview.md`. Read it when planning route selection or explaining available current-project APIs.

Important constraints from the API:

- All API responses use `{success,data,error?}`.
- `project_id` is injected by the MCP token and must not be supplied.
- Use `response_filter` to avoid returning full workspaces, long story text, and signed image URLs unless they are explicitly needed.
