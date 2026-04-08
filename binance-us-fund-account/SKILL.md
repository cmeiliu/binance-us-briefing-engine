---
name: binance-us-fund-account
description: Guide a user through funding a Binance.US account in a safe, explicit workflow. Use when the user wants to add cash, asks how to fund Binance.US, asks why a deposit is pending, or needs the next step after a capital-readiness check.
metadata:
  version: 0.3.0
  author: Binance.US
license: MIT
---

# Binance.US Fund Account

Use this skill when the user is trying to get capital ready on Binance.US.

## Use This Skill For

- "How do I fund my Binance.US account?"
- "What should I do next after capital readiness?"
- "Why is my deposit pending?"
- "How do I add cash so I can buy crypto?"

## When Not To Use

- market summaries
- asset research
- automated trading requests
- off-platform banking or tax advice

## Workflow

1. Confirm whether the user already has Binance.US credentials or account access.
2. If the user has account context, prefer a capital-readiness or account-status check first.
3. If they need instructions, guide them through the next explicit Binance.US action:
   - open Binance.US
   - choose funding method
   - enter amount
   - confirm status after submission
4. If the user reports a pending or failed deposit, route them toward account-status review and state what information matters.

## Handoffs

- If the user wants to know whether it is worth funding now, use `binance-us-briefing-engine` in `capital_readiness` mode first.
- If the user wants to act on a specific asset after funding, hand off to `binance-us-asset-research` or a trading workflow.

## Guardrails

- Keep the guidance explicit and step-by-step.
- Do not pretend funding succeeded if there is no account confirmation.
- Keep the tone neutral and operational, not promotional.
