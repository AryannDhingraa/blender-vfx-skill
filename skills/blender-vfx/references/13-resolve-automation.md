# Automating DaVinci Resolve

Which route works depends on the edition and version. Record the route in `vfx-profile.md`.

| Edition | Route | Notes |
| --- | --- | --- |
| Studio | Blackmagic's built-in MCP server (recent versions), or any MCP server that uses external scripting | Set Preferences, System, General, External scripting using: Local |
| Free 21.1 and later | Lua bridge MCP (`saadk408/davinci-resolve-lua-mcp`) | Python and external scripting moved to Studio in 21.1. A Lua script started from Workspace, Scripts still works |
| Free up to 21.0.x | In-app Python bridge of `samuelgursky/davinci-resolve-mcp` | Needs Python 3.10 to 3.12 visible to Resolve |
| No bridge | Manual | Give the user short numbered steps |

## Lua bridge (Free 21.1+) setup

1. Launch Resolve once so its Scripts folder exists.
2. Install the `.mcpb` from the project's latest release into Claude Desktop and click Install.
3. Every Resolve session: open a project, then Workspace, Scripts, `resolve_mcp_bridge`. It stops when Resolve quits.
4. Test: ask for `resolve_status`.

It has typed tools (projects, timelines, media pool clips, markers, render and render status, API docs search) plus `run_lua` for anything else.

## Rules when driving Resolve

- Confirm the open project and timeline with a status call first. Never switch or open projects without asking.
- Show every `run_lua` chunk that changes something before running it, in a few lines, and wait for approval. Read-only chunks can run directly.
- Keep chunks short. Return counts and names, not full clip dumps.
- Renders: start with the render tool, then poll the status tool. Never wait inside one long call; the bridge handles one request at a time and cannot answer Resolve's dialogs.
- Use `scripting_api_docs` to check a function exists before calling it.
- Never delete media, timelines or render jobs without explicit approval.

## Jobs worth automating

- Import plates and VFX renders into named bins.
- Build a VFX pull timeline: markers on every VFX shot with shot IDs from `shot-log.md`.
- Queue exports of VFX plates (the colour round trip format from `03-color-pipeline.md`) and of final masters (16:9 and 9:16 presets).
- Report render status and file paths back into `shot-log.md`.

Grading stays a human job. Suggest node changes as steps; the user makes the creative calls.
