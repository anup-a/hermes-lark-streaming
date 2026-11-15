# Anup's fork

This is Anup Aglawe's fork of [Cheerwhy/hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming),
running as the live Feishu card plugin for his Hermes agent (Zex).

## Branches

- `main`: mirror of `upstream/main`. Never commit here.
- `anup/main`: what runs. Upstream main plus our changes. The live plugin
  (`~/.hermes/plugins/hermes-lark-streaming`) is checked out on this branch.
- `zex/<topic>`: one branch per change, cut from `anup/main`, merged back with `git merge`.

## Our changes on top of upstream

- HTML code blocks and local images rendered into cards (T3 theme, layout sheet, `html-preview` CLI)
- `card.split_content`: reasoning/tool work and answer text on separate cards

## Remotes and checkouts

- `origin` = `git@github.com:anup-a/hermes-lark-streaming.git` (this fork)
- `upstream` = `https://github.com/Cheerwhy/hermes-lark-streaming`
- Source checkout: `~/hermes-plugin-src/hermes-lark-streaming`. The live plugin's `origin`
  points at it (`file://`), so changes flow: live dir → source checkout → GitHub fork.

## Syncing with upstream

```bash
cd ~/hermes-plugin-src/hermes-lark-streaming
git fetch upstream && git checkout main && git merge --ff-only upstream/main && git push origin main
git checkout anup/main && git merge upstream/main   # merge, never rebase
# run the gates in AGENTS.md, then:
git push origin anup/main
cd ~/.hermes/plugins/hermes-lark-streaming && git pull --ff-only origin anup/main
```

Then restart the gateway (`touch ~/.hermes/state/zex-reload.request`, or `/restart`).

## Upstreaming

A change that is generic (like `split_content`, off by default) can go upstream as a PR from a
`zex/<topic>` branch based on `upstream/main`. Ask Anup before opening it.
