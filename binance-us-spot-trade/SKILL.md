---
name: binance-us-spot-trade
description: Guide a user through reviewing and placing a Binance.US spot trade in a deliberate, safe workflow. Use when the user wants to buy or sell on Binance.US after reviewing a brief or research workflow.
metadata:
  version: 0.3.0
  author: Binance.US
license: MIT
---

# Binance.US Spot Trade

Use this skill when the user is ready to review a spot trade on Binance.US.

## Use This Skill For

- "I want to buy BTC on Binance.US"
- "Help me review a spot trade"
- "What should I check before I place a trade?"
- "I have cash ready, how do I act on this setup?"

## When Not To Use

- broad market summaries
- deeper research on whether an asset is interesting
- derivatives or margin trading
- automatic trading or hidden order placement

## Workflow

1. Confirm the user already knows which asset they are evaluating.
2. If not, hand off to `binance-us-asset-research`.
3. If they are not funded, hand off to `binance-us-fund-account`.
4. If they are ready, guide them through a clear pre-trade review:
   - what asset
   - what side
   - what amount
   - what invalidates the idea
   - what they are waiting for if they are being patient
5. Only after that, summarize the next explicit Binance.US step to execute.

## Handoffs

- Use `binance-us-briefing-engine` for the daily context.
- Use `binance-us-asset-research` for conviction building.
- Use `binance-us-fund-account` if capital is not ready.

## Guardrails

- Do not imply guaranteed outcomes.
- Do not place trades automatically.
- Keep the review explicit enough that the user understands why they are acting.
