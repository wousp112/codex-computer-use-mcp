# Companion Skill: Computer Use Human Mode

This document captures the intended behavior layer that should sit on top of `codex-computer-use-mcp`.

The MCP bridge is only the transport and approval layer. It makes Codex Desktop Computer Use callable from another MCP client.

That alone is not enough.

To make the system genuinely useful, the calling agent should behave like a real person sitting in front of a computer:

- look at the screen
- interpret what is visible now
- click into details when needed
- scroll when the answer is below the fold
- dismiss overlays
- expand collapsed content
- revisit the screen after each action
- use visual understanding when structured text is insufficient

## Design goal

Do not treat Computer Use as a DOM scraper.
Treat it as a human-style desktop operator.

## Core loop

1. orient: confirm current app, window, tab, and screen state
2. observe: read what is visible now
3. identify the gap: what is still missing?
4. act: click, scroll, focus, expand, switch, open details
5. re-check: did the screen change the way a human would expect?
6. repeat until the actual task is complete

## Default policy

The agent should not stop early just because the first screen or accessibility tree does not expose enough text.

Before declaring failure, it should usually attempt:
- scrolling
- opening the detail page
- clicking `Show more` / `Expand`
- dismissing obstructions
- switching to the correct app/window/tab
- reading from the visible screen using vision when necessary

## When this matters most

Especially important for:
- X / social feeds
- YouTube and media-heavy sites
- Notion / Obsidian / document editors
- desktop apps where the visible UI matters more than the accessibility tree

## Limits

This philosophy does not override:
- macOS permission prompts
- login walls
- app crashes
- user decisions that require explicit approval

## Why this exists

Without this behavior layer, a Computer Use integration often degrades into a brittle “read the UI tree once and give up” tool.

The bridge solves connectivity.
This companion skill defines how to use the bridge well.
