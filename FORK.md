# Anup's fork

This is Anup Aglawe's fork of [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming),
running as the live Feishu card plugin for his Hermes agent (Zex).

## Branches

- `main`: the released fork, upstream plus our changes. `anup/main` is merged into it with a merge
  commit (Anup's call, 2026-11-16); it is the GitHub default view.
- `anup/main`: what runs. The live plugin (`~/.hermes/plugins/hermes-lark-streaming`) is checked
  out on this branch; merge it into `main` when a batch of changes is done.
- Upstream is tracked only through the `upstream` remote (`upstream/main`).
- `zex/<topic>`: one branch per change, cut from `anup/main`, merged back with `git merge`.

## Our changes on top of upstream

- HTML code blocks and local images rendered into cards (T3 theme, layout sheet, `html-preview` CLI)
- `card.split_content`: two cards per turn, work and final answer (the answer moves to its own card when the turn ends)
- `card.recover_orphans`: cards left on Processing by a killed gateway are restored from a snapshot and marked Interrupted (idea from wzgrx/hermes-lark-streaming)
- `card.rollover_minutes`: roll over to a new card before Feishu's ~10 min streaming limit (idea from wzgrx)
- `/mention`-friendly per-group rules and topic-group fixes: silent turns recall their card, and
  turns without an inbound message (background-job notices) reply inside their topic
- `card.header.title: conclusion`: the green completed header shows the answer's first line instead of "Completed"

## Remotes and checkouts

- `origin` = `git@github.com:anup-a/hermes-lark-streaming.git` (this fork)
- `upstream` = `https://github.com/Cheerwhy/hermes-lark-streaming`
- Source checkout: `~/hermes-plugin-src/hermes-lark-streaming`. The live plugin's `origin`
  points at it (`file://`), so changes flow: live dir → source checkout → GitHub fork.

## Syncing with upstream

```bash
cd ~/hermes-plugin-src/hermes-lark-streaming
git fetch upstream && git checkout anup/main && git merge upstream/main   # merge, never rebase
# run the gates in AGENTS.md, then:
git push origin anup/main
cd ~/.hermes/plugins/hermes-lark-streaming && git pull --ff-only origin anup/main
# release: merge anup/main into main (merge commit) and push main
```

Then restart the gateway (`touch ~/.hermes/state/zex-reload.request`, or `/restart`).

## Upstreaming

A change that is generic (like `split_content`, off by default) can go upstream as a PR from a
`zex/<topic>` branch based on `upstream/main`. Ask Anup before opening it.
