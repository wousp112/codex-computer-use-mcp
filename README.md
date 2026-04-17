# codex-computer-use-mcp

Expose Codex Desktop's bundled Computer Use plugin as a local MCP server that other MCP clients can call.

It connects to a running `codex app-server`, ensures the bundled `computer-use` plugin is installed, then exposes two MCP tools:

- `codex_computer_use_run`
- `codex_computer_use_status`

This is for people who already have Codex Desktop with Computer Use on a Mac and want to reuse that capability from another agent instead of rebuilding the whole desktop-control stack.

## What it does

- talks to Codex Desktop's websocket app-server
- selects the bundled `computer-use` plugin
- auto-starts `codex app-server` locally if needed
- handles the approval / elicitation round-trip that otherwise causes browser or app access to hang
- returns final answer text, commentary, startup events, and tool failures

## Companion behavior layer

This repo now also documents the intended calling strategy in:

- `docs/skills/computer-use-human-mode.md`

That companion skill exists because a working bridge is not enough. The calling agent should use Computer Use like a real person using a computer:

- observe the screen
- click into details when needed
- scroll when the answer is below the fold
- dismiss overlays
- expand hidden content
- re-check after each action
- prefer visual understanding when the accessibility tree is not enough

The bridge solves connectivity. The skill defines how to use the bridge well.

## What it does not do

- it does not bundle Codex Desktop for you
- it does not bypass macOS permissions
- it does not make desktop automation magically risk-free
- it is not a browser crawler or Playwright wrapper

## Requirements

- macOS
- Python 3.11+
- Codex Desktop installed
- the `codex` CLI available on `PATH`
- a Codex install that includes the bundled `computer-use` plugin

## Install

```bash
git clone https://github.com/YOUR_USERNAME/codex-computer-use-mcp.git
cd codex-computer-use-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Run as an MCP server

```bash
codex-computer-use-mcp
```

It runs over stdio, so you normally launch it from another MCP client.

## Example MCP client config

### Generic stdio MCP config

```json
{
  "mcpServers": {
    "codex-computer-use": {
      "command": "/absolute/path/to/.venv/bin/codex-computer-use-mcp",
      "args": []
    }
  }
}
```

### Hermes example

```yaml
mcp_servers:
  codex_computer_use:
    command: /absolute/path/to/.venv/bin/codex-computer-use-mcp
    args: []
```

## Tools

### `codex_computer_use_status`

Returns whether Codex sees the bundled plugin and where it is loading it from.

### `codex_computer_use_run`

Parameters:

- `prompt` (required): instruction for Codex Computer Use
- `cwd` (optional): working directory for the Codex thread
- `timeout_sec` (optional, default `180`)
- `model` (optional)
- `effort` (optional)
- `thread_mode` (`stateless` or `sticky`, default `stateless`)
- `thread_id` (optional, used with `sticky`)

## Configuration

This project removes the machine-specific hardcoded paths from the original bridge. Configure it through environment variables if the defaults are wrong.

### Supported environment variables

- `CODEX_CU_APP_SERVER_URL`
  - default: `ws://127.0.0.1:8766`
- `CODEX_HOME`
  - default: `~/.codex`
- `CODEX_CU_BUNDLED_MARKETPLACE`
  - default: `$CODEX_HOME/.tmp/bundled-marketplaces/openai-bundled/.agents/plugins/marketplace.json`
- `CODEX_CU_PLUGIN_NAME`
  - default: `computer-use`
- `CODEX_CU_PLUGIN_ID`
  - default: `computer-use@openai-bundled`
- `CODEX_CU_DEFAULT_CWD`
  - default: your home directory
- `CODEX_CU_AUTO_START_APP_SERVER`
  - default: `1`
- `CODEX_CU_APPROVAL_MODE`
  - one of: `known-safe-only`, `always`, `never`
  - default: `known-safe-only`

## Approval handling

This bridge exists largely because Codex app-server may emit `mcpServer/elicitation/request` prompts such as:

- `Allow Codex to use Google Chrome?`

If the caller ignores that request, Computer Use often hangs for about 120 seconds and then fails with a useless timeout.

Default behavior here is conservative:

- `known-safe-only`: auto-accept only the known empty-schema Computer Use app-access prompt
- `always`: accept every elicitation request sent through this bridge
- `never`: decline every elicitation request

Use `always` only if you understand the trade-off.

## macOS permissions you still need

This bridge cannot grant permissions for you. You may still see prompts for:

- Apple Events / automation access to apps like Chrome
- Accessibility
- Screen & System Audio Recording
- the macOS private window picker / screen capture privacy prompt

If Computer Use can see the app but cannot act, the problem is usually macOS permissions, not the bridge.

## Limitations

- tested against Codex Desktop's bundled `computer-use` plugin on macOS
- relies on Codex internal app-server protocol details that may change
- UI accessibility text is not always enough; some tasks still need visual navigation and detail-page opening like a real human would do
- top-level app permissions are outside this project's control

## Local smoke test

Once installed, you can wire it into your MCP client and call:

- `codex_computer_use_status`
- `codex_computer_use_run` with a harmless prompt like `Tell me the current frontmost app.`

## License

MIT
