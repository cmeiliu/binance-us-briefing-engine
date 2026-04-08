---
name: binance-us-briefing-engine
description: Personalized Binance.US market, portfolio, and watchlist briefings using account balances, recent trading history, watchlists, market data, and recent news headlines tied to the user's relevant assets. Use when the user asks for a market summary, personalized crypto brief, portfolio update, funding nudge, watchlist recap, opportunity alert, or weekly reset for Binance.US.
metadata:
  version: 0.1.0
  author: Binance.US
  openclaw:
    skillKey: binance-us-briefing-engine
    requires:
      bins:
        - python3
    homepage: https://skills.sh
license: MIT
---

# Binance.US Briefing Engine

Generate account-aware Binance.US briefings. This skill is only valuable when it ties the market back to the user's own account.

## Use This Skill For

- "Give me a personalized market summary"
- "What matters for my Binance.US account today?"
- "Summarize my watchlist"
- "Give me a portfolio brief"
- "Do I have idle cash or concentration risk?"
- "What changed since my recent trades?"
- "Give me a funding nudge"
- "Give me a weekly reset"

## Core Rule

Prefer account-aware output over generic market commentary.

When credentials are available, use:

- current balances
- recent trading history
- watchlist or configured priority assets
- deposit history when useful
- recent headlines for owned, watched, or recently traded assets

If credentials are unavailable, the script can still produce a limited market-only brief, but it should say so clearly.

## How To Run

Run the bundled script:

```bash
python3 scripts/binance_us_brief.py --mode daily_brief --format both
```

Common variants:

```bash
python3 scripts/binance_us_brief.py --mode portfolio_brief --format text
python3 scripts/binance_us_brief.py --mode watchlist_brief --watchlist BTC,ETH,SOL
python3 scripts/binance_us_brief.py --mode opportunity_alert --alert-threshold-pct 5
python3 scripts/binance_us_brief.py init-config
```

## Credentials

The script will look for Binance.US credentials in this order:

1. Environment variables:
   - `BINANCE_US_API_KEY`
   - `BINANCE_US_SECRET_KEY`
2. `~/.openclaw/secrets.env`
3. `~/.env`
4. `.env` in the current workspace

Optional aliases are also supported:

- `BINANCEUS_API_KEY`
- `BINANCEUS_SECRET_KEY`
- `BINANCE_API_KEY`
- `BINANCE_SECRET_KEY`

The script reads only specific keys and does not print raw secrets.

## Optional Config

The script supports a small JSON config at:

`~/.openclaw/binance-us-briefing-engine.json`

Create it with:

```bash
python3 scripts/binance_us_brief.py init-config
```

Useful fields:

- `watchlist`
- `quote_assets`
- `quiet_hours`
- `recent_days`
- `portfolio_currency`
- `alert_threshold_pct`

## Recommended Workflow

1. Run `daily_brief` for a broad summary tied to balances and recent trades.
2. Run `portfolio_brief` when the user wants account impact, concentration, or idle cash context.
3. Run `watchlist_brief` when the user asks about tracked assets.
4. Use recent news headlines to explain why those assets matter today.
5. Run `funding_nudge` to connect market setup to deposit readiness.
6. Run `opportunity_alert` for trigger-style checks on owned, watched, or recently traded assets.
7. Run `weekly_reset` for a slower, portfolio-aware recap.

## Output Contract

The script returns:

- JSON only
- text only
- or both

The JSON output is the source of truth. The text output is the delivery-ready rendering.

## Guardrails

- Treat the brief as informational, not financial advice.
- Never claim certainty or guaranteed returns.
- Do not place trades automatically.
- If the user requests an action after reading the brief, handle that as a separate explicit step.
