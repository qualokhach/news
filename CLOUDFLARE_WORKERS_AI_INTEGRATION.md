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

## Additional reliability repairs (2026-11-02)
- Provider fallback now runs the full local article validation (`make_article`) before accepting a provider response. A draft that fails fact-ledger, source-independence, risk, or quality checks moves to the next provider instead of stopping after Gemini.
- Cloudflare response parsing accepts both JSON text and structured JSON objects. Invalid body/keyword item types fail with a clear schema error rather than an incidental `.strip()` exception.
- Research grouping now compares each candidate headline to the group's anchor and requires at least two shared meaningful tokens. This prevents transitive chaining of unrelated stories.
- The writing stage filters staged evidence against the lead headline before calling any model. Candidates with fewer than two independent secondary-source families and no claim-supporting primary source are held without API calls.
- A technical writing failure gets one delayed retry after six hours. After two failed writing sessions, the candidate is moved to HOLD for manual review rather than consuming API quota on every scheduled run.
- Grok remains out of the writing provider chain. OpenRouter remains the final fallback and is restricted to models with zero prompt and completion prices.

## Validation performed on this ZIP
- Python compilation: all 29 project Python files passed.
- YAML parse: all workflow YAML files passed.
- `scripts/audit_site.py`: passed (active=77, archived=43, catalog=43, pending=5000, research_ready=0).
- Offline regression suite: 101 tests passed.
- Current staged queue preflight: 4 WRITING_PENDING candidates; 2 retain enough relevant independent sources to attempt writing; 2 are held before any AI call because their apparent second source is about a different event.
- Live Cloudflare API was not called during local validation; the user's successful GitHub Actions test #6 remains the live API confirmation.
