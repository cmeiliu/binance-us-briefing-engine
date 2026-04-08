---
name: binance-us-asset-research
description: Research a Binance.US-listed crypto asset using the shared Binance.US engine. Use when the user asks for deeper research on a specific asset, wants a structured Binance.US-safe coin overview, or asks what is happening with BTC, ETH, SOL, or another listed asset.
metadata:
  version: 0.2.0
  author: Binance.US
license: MIT
---

# Binance.US Asset Research

Use this skill for deeper single-asset analysis after a brief surfaces an idea worth investigating.

## Use This Skill For

- "Research BTC"
- "Look at SOL"
- "What is happening with ETH?"
- "Give me a Binance.US-safe overview of AVAX"
- "Should I spend time on this asset?"

## When Not To Use

- broad market summaries
- portfolio-only reviews
- funding or cash-readiness checks
- fully automated trading or execution requests

## How To Run

Run the shared engine in research mode:

```bash
python3 scripts/binance_us_brief.py --mode asset_research --asset BTC --format text
```

You can also use `--watchlist BTC,ETH,SOL` and omit `--asset`, but explicit `--asset` is better for determinism.

## Research Contract

The output should be structured and Binance.US-safe:

- overview
- market structure
- market context
- catalyst watch
- risk factors
- a next-step prompt that sends the user back into Binance.US if the asset deserves attention

Keep it informational. Do not present it as guaranteed returns or one-sided trading advice.
