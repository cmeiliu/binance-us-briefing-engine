---
name: binance-us-account-status
description: Review Binance.US account readiness, balances, deposits, pending states, and operational blockers. Use when the user asks what is happening in their account, why something is pending, or whether they are ready to act.
metadata:
  version: 0.3.0
  author: Binance.US
license: MIT
---

# Binance.US Account Status

Use this skill when the user needs operational clarity before taking action.

## Use This Skill For

- "What is happening in my Binance.US account?"
- "Why is my deposit pending?"
- "Am I ready to trade?"
- "What balances do I actually have available?"

## When Not To Use

- broad market summaries
- single-asset research
- trade ideation without account context

## Workflow

1. Check whether account credentials are available.
2. If they are not, say so clearly and switch to market-only fallback guidance.
3. If they are, summarize:
   - balances
   - idle cash
   - deposit recency or pending status
   - concentration or readiness blockers
4. Route the user to the right next skill:
   - `binance-us-fund-account`
   - `binance-us-spot-trade`
   - `binance-us-briefing-engine`

## Guardrails

- Stay operational and factual.
- Do not claim a deposit is complete unless account data confirms it.
- Do not blend account-status questions with speculative market advice.
