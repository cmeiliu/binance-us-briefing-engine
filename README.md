# Binance.US Briefing Engine

`Binance.US Briefing Engine` is a portable skill workflow for OpenClaw, Codex, and Claude Code. It generates personalized Binance.US briefs using:

- account balances
- recent trading history
- watchlists
- market data
- recent asset-specific news

The goal is to produce a brief that explains what matters for a specific user, not just what happened in the market.

## Features

- `daily_brief`
- `portfolio_brief`
- `watchlist_brief`
- `opportunity_alert`
- `funding_nudge`
- `weekly_reset`
- price-anchored summaries with 24h and 7-day context
- portfolio-aware news ranking and de-duplicated asset headline search
- Markdown-friendly text output for chat delivery
- first-run hook, watchlist-gap prompts, and sharper action-oriented CTAs

## Install

### OpenClaw

Local path:

```bash
npx skills add /path/to/binance-us-briefing-engine -g --agent openclaw --yes --copy
```

From GitHub after publishing:

```bash
npx skills add <github-owner>/<github-repo> -g --agent openclaw --yes --copy
```

### Codex

Codex can use this repo directly. The Codex-facing workflow is documented in [AGENTS.md](/Users/meiliu/codex/binance%20us%20skills/AGENTS.md), and the shared engine is:

```bash
python3 scripts/binance_us_brief.py --mode daily_brief --format text
```

### Claude Code

Claude Code can use the project-local skill wrapper at [.claude/skills/binance-us-briefing-engine/SKILL.md](/Users/meiliu/codex/binance%20us%20skills/.claude/skills/binance-us-briefing-engine/SKILL.md).

It invokes the same bundled Python engine, so behavior stays aligned across agents.

## Usage

In OpenClaw:

```text
Use $binance-us-briefing-engine to generate a personalized Binance.US brief from my balances, recent trades, and watchlist.
```

From the command line:

```bash
python3 scripts/binance_us_brief.py --mode daily_brief --format text
python3 scripts/binance_us_brief.py --mode portfolio_brief --format both
python3 scripts/binance_us_brief.py --mode watchlist_brief --watchlist BTC,ETH,SOL
```

This script is the shared execution layer for OpenClaw, Codex, and Claude Code.

## Credentials

Each user must provide their own Binance.US credentials. Nothing is hard-coded into the skill.

Supported variables:

- `BINANCE_US_API_KEY`
- `BINANCE_US_SECRET_KEY`

Recommended location:

- `~/.openclaw/secrets.env`

Example:

```bash
BINANCE_US_API_KEY=your_key_here
BINANCE_US_SECRET_KEY=your_secret_here
```

Only these exact variable names are supported.

## Safety

This skill is read-only.

It does not:

- place orders
- convert assets
- move funds
- modify account settings

Allowed outbound network domains:

- `api.binance.us`
- `news.google.com`

The skill reads only user-provided Binance.US credentials and does not embed shared credentials in code.

## Config

Optional config file:

`~/.openclaw/binance-us-briefing-engine.json`

Create a starter config with:

```bash
python3 scripts/binance_us_brief.py init-config
```

## License

MIT
