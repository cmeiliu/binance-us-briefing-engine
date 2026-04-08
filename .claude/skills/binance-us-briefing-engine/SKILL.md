---
name: binance-us-briefing-engine
description: Generate personalized Binance.US market briefs, watchlist recaps, opportunity alerts, funding nudges, portfolio summaries, and weekly resets using the bundled Python engine and optional user-provided Binance.US credentials.
---

# Binance.US Briefing Engine

Use this skill when the user asks for:

- a Binance.US market summary
- a personalized crypto brief
- a watchlist recap
- an opportunity alert
- a funding nudge
- a portfolio brief
- a weekly reset

Run the bundled script:

```bash
python3 scripts/binance_us_brief.py --mode daily_brief --format text
```

Useful variants:

```bash
python3 scripts/binance_us_brief.py --mode watchlist_brief --watchlist BTC,ETH,SOL --format text
python3 scripts/binance_us_brief.py --mode opportunity_alert --watchlist BTC,ETH,SOL --format text
python3 scripts/binance_us_brief.py --mode funding_nudge --watchlist BTC,ETH,SOL --format text
python3 scripts/binance_us_brief.py --mode weekly_reset --watchlist BTC,ETH,SOL --format text
python3 scripts/binance_us_brief.py --mode portfolio_brief --format text
```

Credentials, when available:

- `BINANCE_US_API_KEY`
- `BINANCE_US_SECRET_KEY`

If credentials are unavailable, the script returns a clearly labeled market-only brief.

Keep the output informational. The script already frames both the bull case and the case for patience.
