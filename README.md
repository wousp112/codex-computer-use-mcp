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
git clone https://github.com/wousp112/codex-computer-use-mcp.git
cd codex-computer-use-mcp
python3.11 -m venv .venv  # strongly preferred on macOS; plain `python3` may bind to an older interpreter
source .venv/bin/activate
python --version          # should report 3.11+
pip install -U pip
pip install -e .
```

If `python3.11` is not on your PATH, use any explicit Python 3.11+ interpreter path instead.

## Run as an MCP server

```bash
codex-computer-use-mcp
```

It runs over stdio, so you normally launch it from another MCP client.

## Quickstart

For a first-time local check, the shortest path is:

1. install the package in a fresh Python 3.11+ venv
2. add the MCP config using `examples/hermes-config.yaml` or `examples/mcp-config.json`
3. restart your MCP client if needed
4. call `codex_computer_use_status`
5. then call `codex_computer_use_run` with:
   - `Tell me the current frontmost app.`

If step 4 works but step 5 hangs, do not guess: jump straight to `Approval handling` and `Common failure modes` below.

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

Once installed, wire it into your MCP client and verify in this order:

1. `codex_computer_use_status`
   - confirms the bridge starts
   - confirms Codex is reachable
   - confirms the bundled plugin is visible
2. `codex_computer_use_run` with a harmless prompt like `Tell me the current frontmost app.`
   - confirms an actual turn works end-to-end
3. if browser/app access hangs or times out, check the `Approval handling` section above before assuming the bridge is broken

## Common failure modes

### 1. `codex_computer_use_status` works, but `codex_computer_use_run` hangs or times out

Most likely cause:
- an MCP elicitation / approval request was emitted by Codex and not handled the way you expect

What to check:
- read `Approval handling`
- verify `CODEX_CU_APPROVAL_MODE`
- remember that browser/app access may trigger prompts like `Allow Codex to use Google Chrome?`

### 2. The bridge starts, but Computer Use can see apps and cannot act on them

Most likely cause:
- macOS permissions are missing or incomplete

What to check:
- Accessibility
- Apple Events / automation access
- Screen Recording / privacy prompts

### 3. Install succeeds, but the package runs under the wrong Python

Most likely cause:
- your venv was created with an older interpreter instead of Python 3.11+

What to check:
- run `python --version`
- if needed, recreate the venv explicitly with `python3.11 -m venv .venv`

### 4. The MCP client config looks right, but nothing works

What to check:
- make sure the command path really points at the installed `codex-computer-use-mcp` executable inside your venv
- restart the MCP client after editing config
- test `codex_computer_use_status` before trying a real task

### 5. The bridge is fine, but Codex Desktop itself is not ready

What to check:
- Codex Desktop is installed
- the `codex` CLI is on `PATH`
- the bundled `computer-use` plugin exists in your Codex install
- if auto-start is disabled, a reachable `codex app-server` is already running

## License

MIT
