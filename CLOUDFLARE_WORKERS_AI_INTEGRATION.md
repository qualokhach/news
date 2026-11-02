# AppNho News — Cloudflare Workers AI integration

## Scope
- Add `@cf/meta/llama-3.3-70b-instruct-fp8-fast` as the second article-drafting provider.
- Keep Gemini first and OpenRouter free-only as the next fallback.
- Stop calling Grok/xAI from the article-writing fallback. Existing Grok GitHub Secret is not deleted.
- Pass `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` to the publication workflow.
- Correct the OpenRouter Secret mapping to `OPENROUTER_API_APPNHO_NEWS`, matching the repository Secret name.

## Usage guardrails
- Cloudflare inference is capped at 3 calls per publication run by default (`MAX_CLOUDFLARE_CALLS_PER_RUN`).
- The same evidence-bound prompt is used; provider changes do not bypass editorial validation or publication checks.
- Cloudflare usage is subject to the account's current Workers AI quota and pricing. The cap limits calls; it is not a guarantee that usage is free.

## Validation performed on this ZIP
- Python compilation: passed.
- YAML parse of `build-news.yml`: passed.
- `scripts/audit_site.py`: passed (active=77, archived=43, catalog=43, pending=5000, research_ready=0).
- Offline regression suite: 95 tests passed.
- Live Cloudflare API was not called during local validation; the user's successful GitHub Actions test #6 remains the live API confirmation.
