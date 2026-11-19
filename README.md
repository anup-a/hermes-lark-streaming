# Hermes Lark Streaming (Anup's fork)

[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[中文 (upstream)](README.zh.md) · [Fork notes](FORK.md) · Upstream: [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming)

Feishu/Lark CardKit 2.0 streaming cards for **Hermes >= 0.22.0**. Every reply from the agent is a
live card: reasoning and tool calls stream into collapsible panels, the answer streams as Markdown,
and a footer shows status, time, context and model. It runs inside the Hermes gateway as a native
platform plugin (it subclasses the built-in Feishu adapter), with no source patches or sidecar.

This fork runs **Zex**, Anup Aglawe's agent on Lark. It adds the features below on top of upstream.
Each one sits behind an option under `platforms.feishu.extra.card`, off by default, so the plugin
behaves like upstream until you turn them on.

## What this fork adds

### Two cards per turn: work and answer (`split_content: true`)
- The **work card** holds reasoning, tool calls and the agent's in-between progress notes. No
  "Done." filler.
- The **answer card** holds only the final reply, with the footer.
- The reply streams on the work card while the agent works, then moves to its own card when the
  turn ends, so the chat history reads as one clean answer per question.
- Plain text replies, errors and stopped turns stay on one card. If the answer card cannot be sent,
  everything stays on the work card, so nothing is lost. A tool result that arrives after the reply
  does not post the reply twice.

### Cards never stay stuck on "Processing..." (`recover_orphans: true`)
- Open cards are registered in `~/.hermes/state/hermes-lark-streaming-open-cards.json`, with a
  snapshot of the card in its "Interrupted" form saved every 5 seconds while it streams.
- If the gateway is killed or crashes mid-turn, the next message replaces any card left on
  "Processing..." (older than 60 s) with its last snapshot, so you keep what was already shown.
  It checks again every 5 minutes and gives up on a card after 3 failed attempts.

### Long turns don't freeze at 10 minutes (`rollover_minutes: 8`)
- Feishu stops a card's streaming after about 10 minutes. Past the configured age, the card is
  sealed with "Continued in the next card" and the turn carries on in a new one. The segment still
  being written moves across whole, so nothing is duplicated.

### Verdict title, colour and folded details (`header.title: verdict`, `fold_details`)

The agent starts its answer with a status mark, e.g. `⚠️ Root cause: ByteMock timed out`. The line moves
into the header and the mark picks the colour (✅ green, ⏳ blue, ⚠️ orange, ❌ red), so a glance at the
chat shows which answers need attention. Evidence and next steps go under a standalone
`**Evidence and what to do**` line, which folds into a collapsed panel so the card shows only the
verdict and a short summary. Inspired by the KeyClaw bot's `set_final_card` output.

### Conclusion as the card title (`header.title: conclusion`)
- The green "Completed" header shows the first line of the final answer instead (Markdown
  stripped, up to 80 characters). Errors and stops keep their status title.

### Card clicks reach the agent (`card_actions_to_agent: true`)
- Clicks on cards the bot sent itself (buttons, selects, form submits; not Hermes's own approval or
  clarify cards) arrive as a normal message `[Card action] {...}` with `card_message_id`, `tag`,
  `value`, `form_value`, `input_value`, `option(s)` and `checked`, replying to the card.
- Without it, Hermes turns the click into an unknown `/card` command and drops the form values.

### HTML and images inside cards
- ```` ```html ```` blocks in the answer are rendered by headless Chromium (JS runs, so canvas and
  SVG charts work), trimmed to the content height and uploaded as a card image. Theme variables
  follow T3 Code's light theme.
- Markdown images pointing at local files (absolute path or `file://`), such as screenshots the
  agent took, are uploaded and shown inline. Remote image URLs work as before.
- Static cards (cron results, background notices, `hermes send`) get the same treatment.
- Preview a page before sending it: `python -m hermes_lark_streaming.streaming.html_render page.html [out.png]`.

### Topic groups (Lark "topic chat")
- Turns that have no inbound message, such as a background job's completion notice, reply inside
  the topic they belong to instead of opening a new topic.
- A turn that ends with nothing to show (the agent chose to stay silent) recalls its placeholder
  card instead of leaving an empty "Done." card behind.
- Fix: the end-of-turn refresh runs under the flush lock, so a card is never split twice.

### Zex's configuration

```yaml
platforms:
  feishu:
    extra:
      card:
        enabled: true
        header:
          enabled: true
          title: verdict
        split_content: true
        recover_orphans: true
        rollover_minutes: 8
        card_actions_to_agent: true
        fold_details: true
        footer:
          fields:
            - [status, elapsed, context]
            - [tokens, model]
```

Ideas for `recover_orphans` and `rollover_minutes` come from
[wzgrx/hermes-lark-streaming](https://github.com/wzgrx/hermes-lark-streaming), re-implemented for
this card layout: we swap in a full card snapshot because the "Processing..." header cannot be
changed by a partial update.

## Branches

- `main`: this fork's release, upstream plus the changes above.
- `anup/main`: what runs live; merged into `main` with a merge commit when a batch is done.
- Upstream is tracked through the `upstream` remote. See [FORK.md](FORK.md) for syncing.

---

The rest of this README is the upstream reference, updated for this fork.

## Requirements

- Hermes **>= 0.22.0** with the built-in Feishu channel configured
- Python >= 3.11; Hermes manages its own runtime environment
- `lark-oapi >= 1.6.4`, `PyYAML >= 6.0`
- Feishu app permissions for sending/replying to messages, CardKit access and any media features used

Read the [migration guide](MIGRATION.md) before upgrading: remove old injections using the OLD release before installing this version.

## Installation

```bash
hermes plugins install https://github.com/anup-a/hermes-lark-streaming
hermes plugins enable hermes-lark-streaming
hermes gateway restart
```

For local development, symlink the repository to `~/.hermes/plugins/hermes-lark-streaming`, then enable the plugin and restart as above. Restart the Gateway after source changes.

The plugin replaces the `feishu` presentation adapter through the native platform registry. Existing channel settings, credentials, sessions and cron targets stay in place.

## Configuration

Edit the active Hermes profile's `config.yaml` (default: `~/.hermes/config.yaml`). Merge these settings with your existing Feishu connection and access rules.

### Minimal setup

```yaml
streaming:
  enabled: true

platforms:
  feishu:
    enabled: true
    extra:
      card:
        enabled: true

display:
  platforms:
    feishu:
      tool_progress: 'off'
      show_tool_use: true
      show_reasoning: false
```

Hermes's master switch `streaming.enabled` defaults to `false` and must be enabled. Do not set `streaming.transport: off` or `display.platforms.feishu.streaming: false`.

### Card options

All keys below are relative to `platforms.feishu.extra.card`. Unset values use these defaults. Appearance options apply to streaming cards and their final state; standalone cron and background deliveries use a simple fixed layout.

| Key | Default | Effect |
| --- | --- | --- |
| `enabled` | `true` | Enable native streaming cards; `false` disables streaming integration, not the entire plugin |
| `width_mode` | `default` | `default`, `compact` or `fill`; invalid values fall back to `default` |
| `panel_expanded` | `false` | Keep reasoning and tool panels expanded after completion; otherwise collapse them |
| `split_content` | `false` | Two cards per turn: work (reasoning, tools, interim notes) and the final answer with the footer; the answer moves to its own card when the turn ends |
| `recover_orphans` | `false` | Keep a registry and periodic snapshot of open cards in `state/`; after a gateway crash or kill, the next turn replaces cards left on Processing with their last snapshot, marked Interrupted |
| `rollover_minutes` | `0` | Feishu closes a card's streaming after about 10 minutes; past this age, seal the card with "Continued in the next card" and continue on a new one (`0` disables; `8` recommended) |
| `card_actions_to_agent` | `false` | Route clicks on the bot's own cards to the agent as a `[Card action] {...}` message with form and input values, instead of Hermes's `/card` command |
| `header.enabled` | `false` | Show the status header |
| `header.title` | `status` | Completed-card header title: `status` ("Completed"), `conclusion` (first line of the final answer, Markdown stripped, up to 80 chars) or `verdict` (a first line starting with ✅ / ⏳ / ⚠️ / ❌ becomes the title and leaves the body; the mark sets the colour green / blue / orange / red; unmarked answers fall back to `conclusion`). Errors and stops keep their status |
| `fold_details` | `false` | A standalone `**Details**`, `**Evidence…**` or `**How I checked…**` line (bold or `#` heading) folds the rest of the answer into a collapsed panel |
| `body.text_size` | `normal_v2` | Answer Markdown font size; use a CardKit-supported size token |
| `footer.enabled` | `true` | Show the final footer |
| `footer.text_size` | `notation` | Footer font size; use a CardKit-supported size token |
| `footer.fields` | `[[status, elapsed, context, model]]` | Footer fields and ordering; see below |
| `footer.show_label` | `false` | Add labels to duration and context |

For example, merge this appearance configuration under your existing `card`:

```yaml
width_mode: fill
panel_expanded: true
header:
  enabled: true
body:
  text_size: normal_v2
```

### Footer layout

Each inner array in `footer.fields` defines one row; fields within a row are separated by `·`. The following five fields are supported. Fields without data are omitted.

| Field | Content |
| --- | --- |
| `status` | Completed, error or stopped |
| `elapsed` | Card duration |
| `context` | Latest request's full prompt / host context limit and percentage, including cached input |
| `tokens` | Accumulated usage for this turn: `↑` uncached input, `↓` output; full input is used if that is all the host provides |
| `model` | Model name |

For a two-row footer, set this under `platforms.feishu.extra.card`:

```yaml
footer:
  enabled: true
  text_size: notation
  show_label: true
  fields:
    - [status, elapsed]
    - [tokens, model]
```

A flat array such as `[status, elapsed]` creates one row. An empty array restores the default layout; use `footer.enabled: false` to hide the footer. `context` is omitted if the prompt count or context limit is unavailable. The default is one row of `[status, elapsed, context, model]`; add `tokens` as needed.

### Reasoning and tools

| Configuration path | Default | Effect |
| --- | --- | --- |
| `display.platforms.feishu.show_tool_use` | `true` | Show tool names, short arguments, status and duration; omit full successful results |
| `display.platforms.feishu.show_reasoning` | `false` | Show reasoning provided by the model; also enable the event switch below |
| `plugins.stream_reasoning_deltas` | `false` | Allow Hermes to send streaming reasoning events to plugins |
| `display.platforms.feishu.tool_progress` | Set by Hermes | Set to `'off'` to avoid duplicating the plugin's tool panel with host progress text |

For `show_tool_use` and `show_reasoning`, precedence is Feishu-specific setting → the same key under global `display` → the default above. To display reasoning:

```yaml
plugins:
  stream_reasoning_deltas: true
display:
  platforms:
    feishu:
      show_reasoning: true
```

Display switches do not restrict tool permissions or make a model provide reasoning it does not emit.

### Applying changes and channel settings

Run `hermes gateway restart` after changing card options or host streaming settings. `show_tool_use` and `show_reasoning` are reread at runtime for subsequent rendering; completed historical cards are not proactively refreshed.

Keep using Hermes's built-in Feishu credentials (`FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_DOMAIN`) and connection/group settings under `platforms.feishu.extra`. Do not place them under `card`. This plugin adds no channel permission settings.

Legacy card options move from `streaming.*` to `platforms.feishu.extra.card`; the global `streaming.enabled` stays in place. Configuration is not automatically migrated; see the [migration guide](MIGRATION.md).

Approval follow-ups are delivered as final static cards under the Hermes 0.22.0 protocol; clarification can reopen streaming. Clarification uses the built-in text reply flow, and approval buttons retain built-in callbacks.

## Card Preview

Streaming answers with reasoning and tool panels; long content automatically splits across cards.

![Streaming card](assets/streaming.jpg)

Stopping with `/stop`:

![Stopped card](assets/abort.jpg)

Interrupting an active response with a new message:

![Interrupted response](assets/interrupt.jpg)

Screenshots show the existing renderer; appearance depends on card settings and the host version. This fork runs live on Lark as Zex's reply renderer.

## Disabling and diagnostics

```bash
hermes plugins disable hermes-lark-streaming
hermes gateway restart
```

Disabling restores built-in Feishu rendering. `python -m hermes_lark_streaming verify` checks local native interfaces and leftover injections without sending messages or changing configuration. The old patch commands `install`, `uninstall` and `restore` have been removed.

## Development and validation

Install the plugin and a fixed Hermes 0.22.0 checkout in an isolated development environment, then run:

```bash
python -m pip install -e '.[dev]'
python -m ruff check hermes_lark_streaming tests scripts __init__.py
python -m mypy hermes_lark_streaming scripts
python -m pytest tests -q
```

The plugin reuses the built-in Feishu adapter and host message context, including private interfaces. Recheck compatibility after upgrading Hermes.

CI covers Hermes 0.22.0 and 0.22.5 with mocked Feishu APIs and real Hermes registries and stream consumers. Live Feishu messaging requires separate acceptance testing.

For real outbound checks, set `FEISHU_E2E_APP_ID` and `FEISHU_E2E_APP_SECRET`, then run `python scripts/feishu_smoke.py --chat-id <test-chat-id> --scenario all`. It sends fixed test cards for streaming, sequence recovery, splitting, stopping and static updates; add `--reply-to <message-id>` to check quoted replies. No model or tools run. Inbound permissions, clarification and Cron scheduling still need manual acceptance.

## Contributors

Thanks to our contributors for their issues and pull requests:

<a href="https://github.com/Mxin-9527"><img src="https://avatars.githubusercontent.com/u/178271393?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/gitteeee"><img src="https://avatars.githubusercontent.com/u/128769493?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/Bandersnatch0x"><img src="https://avatars.githubusercontent.com/u/13325067?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/runfali"><img src="https://avatars.githubusercontent.com/u/39327978?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/thunderfight127-svg"><img src="https://avatars.githubusercontent.com/u/275854191?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/willggy"><img src="https://avatars.githubusercontent.com/u/74762604?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/atomperson"><img src="https://avatars.githubusercontent.com/u/14934637?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/linjunxin01"><img src="https://avatars.githubusercontent.com/u/63715504?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/mouxangithub"><img src="https://avatars.githubusercontent.com/u/48978046?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/numuly"><img src="https://avatars.githubusercontent.com/u/137970054?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/wzgrx"><img src="https://avatars.githubusercontent.com/u/39661556?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>
<a href="https://github.com/zhaomingcheng01"><img src="https://avatars.githubusercontent.com/u/46734892?v=4&s=64" width="48" height="48" style="border-radius:50%" /></a>

Inspired by [openclaw-lark](https://github.com/larksuite/openclaw-lark) and [hermes-feishu-streaming-card](https://github.com/baileyh8/hermes-feishu-streaming-card).

## License

[MIT](LICENSE)
