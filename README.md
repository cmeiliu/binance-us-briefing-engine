# Binance.US Briefing Engine

`Binance.US Briefing Engine` is the headline skill in a small Binance.US skill family for OpenClaw, Codex, and Claude Code. It generates personalized Binance.US briefs using:

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
- `capital_readiness`
- `weekly_reset`
- `asset_research`
- price-anchored summaries with 24h and 7-day context
- market context and catalyst-watch sections
- portfolio-aware news ranking and de-duplicated asset headline search
- Markdown-friendly text output for chat delivery
- first-run hook, watchlist-gap prompts, and sharper action-oriented CTAs

## Install

### OpenClaw

Local development:

Prefer the default install behavior without `--copy` so your installed skill stays linked to the repo checkout and updates when you pull new commits.

```bash
npx skills add /path/to/binance-us-briefing-engine -g --agent openclaw --yes
```

From GitHub or for snapshot installs:

```bash
npx skills add <github-owner>/<github-repo> -g --agent openclaw --yes --copy
```

To refresh a copied or GitHub-installed skill later:

```bash
npx skills update
```

To discover the full skill family in this repo:

```bash
npx skills add <github-owner>/<github-repo> --list --full-depth
```

To install the companion research skill specifically:

```bash
npx skills add <github-owner>/<github-repo> -g --agent openclaw --yes --full-depth --skill binance-us-asset-research
```

### Codex

Codex can use this repo directly. The Codex-facing workflow is documented in [AGENTS.md](/Users/meiliu/codex/binance%20us%20skills/AGENTS.md), and the shared engine is:

```bash
python3 scripts/binance_us_brief.py --mode daily_brief --format text
```

For deeper single-asset work:

```bash
python3 scripts/binance_us_brief.py --mode asset_research --asset BTC --format text
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
python3 scripts/binance_us_brief.py --mode capital_readiness --format text
python3 scripts/binance_us_brief.py --mode asset_research --asset BTC --format text
```

This script is the shared execution layer for OpenClaw, Codex, and Claude Code.

If you install from GitHub or with `--copy`, the rendered brief also includes a version/update reminder so users get nudged toward `npx skills update`.

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

## Skill Family

- `binance-us-briefing-engine`: daily brief, watchlist, opportunity, portfolio, weekly, and capital-readiness flows
- `binance-us-asset-research`: deeper single-asset research for Binance.US-listed assets

The second skill is packaged in:

- [binance-us-asset-research/SKILL.md](/Users/meiliu/codex/binance%20us%20skills/binance-us-asset-research/SKILL.md)

For repos with a root skill, nested skills may require `--full-depth` during discovery or installation.

## License

MIT
