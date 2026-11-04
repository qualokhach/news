# AppNho News — AI provider order and cost guardrails

Provider order for article drafting is Gemini → Cloudflare Workers AI → OpenRouter.

- Gemini: the pipeline intersects the authenticated `models.list` response with the configured free-tier text-model allowlist. A model is used only when the API reports `generateContent`.
- Cloudflare Workers AI: uses the fixed, preflight-tested model `@cf/meta/llama-3.3-70b-instruct-fp8-fast` through the account REST API. It is the second provider after Gemini. Calls are capped at 3 per publication run by default (`MAX_CLOUDFLARE_CALLS_PER_RUN`) to limit consumption of the Workers AI daily free allowance. A valid API response does not imply unlimited or permanently free usage; Cloudflare's current account quota and pricing apply.
- OpenRouter: only models ending in `:free` with both prompt and completion prices equal to zero are eligible. An explicit `OPENROUTER_MODEL` cannot bypass this check.

Grok/xAI is no longer called by the article-writing fallback. Its GitHub Secret is left untouched and may remain available for separate diagnostics until the repository is deliberately cleaned up.

All providers receive the same evidence-bound editorial prompt. Provider fallback does not bypass JSON parsing, minimum article length, source verification, fact-ledger checks, duplication checks, risk rules, or the final publication gate. A model response is only a draft; it is not automatically publishable.

Gemini calls are capped at 24 per run by default (`MAX_GEMINI_CALLS_PER_RUN`); Cloudflare calls at 3 (`MAX_CLOUDFLARE_CALLS_PER_RUN`); OpenRouter free-model calls at 8 (`MAX_OPENROUTER_CALLS_PER_RUN`). The pipeline records provider/model selection in the article metadata and run logs. OpenRouter is restricted to explicitly zero-priced models; Cloudflare consumption remains subject to the account's applicable daily allowance and pricing.
