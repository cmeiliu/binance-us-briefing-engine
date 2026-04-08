# Binance.US Briefing Engine

This repository contains a portable Binance.US briefing workflow.

When the user asks for a Binance.US market brief, watchlist recap, opportunity alert, capital readiness check, portfolio brief, weekly reset, or deeper asset research, run the bundled Python script instead of rebuilding the logic manually.

## Entrypoint

```bash
python3 scripts/binance_us_brief.py --mode daily_brief --format text
```

Useful modes:

- `daily_brief`
- `watchlist_brief`
- `opportunity_alert`
- `capital_readiness`
- `weekly_reset`
- `portfolio_brief`
- `asset_research`

Useful flags:

- `--watchlist BTC,ETH,SOL`
- `--asset BTC`
- `--format text|json|both`
- `--limit 6`
- `--news-limit 3`

## Credentials

This workflow is read-only and expects only user-scoped Binance.US credentials:

- `BINANCE_US_API_KEY`
- `BINANCE_US_SECRET_KEY`

If credentials are not present, the script falls back to a clearly labeled market-only mode.

## Output expectations

Prefer the script's rendered text output for delivery. It already includes:

- actual prices
- 24h and 7-day framing
- market context and catalyst watch
- watchlist gaps
- cash and funding framing
- a balanced bull case and case for patience

Keep the brief informational. Do not present the output as financial advice.
