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

## Layer 1: default prohibitions

Unless the user explicitly asks and accepts the trade-off, do not:

- use CDP, Playwright, Selenium, or other browser-internal automation interfaces
- rely on DOM scraping, source extraction, in-page script injection, or browser-engine remote control
- treat the browser as a programmable engine instead of a desktop app inside a wider desktop-control task
- bypass the human-style desktop path just to get the answer faster

Why:
- lower JS-environment anomaly risk
- lower automation-exposure risk
- lower browser-kernel / fingerprint / automation-trace risk

## Layer 2: default allowed aids

These are allowed by default:

- screen observation and visual understanding
- accessibility tree as a UI-semantic aid
- app-state snapshot as a current-app-state aid
- human-style desktop actions such as clicking, scrolling, expanding, opening details, dismissing overlays, and switching windows/tabs

Important:
- do not ban accessibility tree or app-state snapshot by default
- they are usually not directly observable by the target platform as a first-class anti-bot signal
- the bigger operational risk is still mechanical, high-frequency, bulk, or repetitive on-platform behavior

## When this matters most

Especially important for:
- X / social feeds
- YouTube and media-heavy sites
- Notion / Obsidian / document editors
- desktop apps where the visible UI matters more than the accessibility tree

## Layer 3: optional Strict Human-Visibility Benchmark Mode

This layer is optional, not default.

status: false

Natural-language switch:
- if `status = true`, also apply the strict benchmark rules below
- if `status = false`, ignore the strict benchmark rules below and continue with the default execution layers

When `status = true`:
- only count content actually brought into view through real desktop actions
- or content made visible by an explicit detail-page / expand action
- do not silently count extra text exposed only by the accessibility tree or app-state snapshot as if it had already been read by a human in the viewport
- if snapshot-only text helps orientation, label it clearly as auxiliary rather than human-visible reading

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
