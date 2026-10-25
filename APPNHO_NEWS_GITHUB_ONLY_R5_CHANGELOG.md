# AppNho News R5 — final pre-commit package

## Versioning
R5 supersedes the corrected R4 package. R4 remains an unchanged reference version; this package is not named R3 or R4.

## Required behavior implemented
- Preserves the initial 43 historical articles and the three manually backfilled daily briefings dated 23–25 October 2026.
- Maps the user's existing GitHub repository secrets to the pipeline environment variables:
  - `GEMINI_API_KEY_APPNHO_NEWS` -> `GEMINI_API_KEY`
  - `GROK_API_APPNHO_NEWS` -> `GROQ_API_KEY`
  - `OPENROUTER_API_APPNHO_NEWS` -> `OPENROUTER_API_KEY`
- Automatic pipeline discovers enabled RSS/Atom leads, deduplicates, fetches public source pages, drafts independently with AI, rejects inadequate drafts, stores new articles in `data/articles.json`, and rebuilds RSS/sitemap.
- Model selection is limited to explicitly identified free candidates: Gemini free-tier allowlist intersected with models returned by the key; Groq Free Plan model IDs intersected with live model list; OpenRouter models must have `:free` suffix and zero prompt/completion pricing. No paid model fallback is allowed by discovery logic.
- Adds `test-ai-apis.yml`, a manual-dispatch preflight workflow that checks each secret's authentication/model discovery without generating or publishing an article. It never prints key values.
- Corrects supplemental source links so the article page can render them, and avoids counting duplicate generated IDs as newly published.
- Retains 30-day archive rotation. The rotation script refuses to overwrite a closed batch and updates catalog/manifest when a batch is closed.
- Existing article URLs continue to use `article.html?id=...`; the static site remains GitHub Pages-compatible.

## Tests run locally
- Python syntax compilation for all scripts.
- JavaScript syntax checks for `assets/app.js` and `assets/article.js`.
- JSON parsing of active/archive/catalog/manifest/pending/dedup data and feed configuration.
- XML parsing of RSS and sitemap after regeneration.
- Structural checks for 43 initial archive articles, 3 backfilled articles (23–25 Oct), unique IDs and expected secret mappings.
- Archive rotation simulated in an isolated copy with old article dates; confirmed batch file, catalog, manifest and active file behavior, including no overwrite.
- Model selection functions unit-tested with mocked provider responses; paid/unknown models excluded.

## Limitations that cannot be verified from a local ZIP
- Real API key acceptance requires running `AppNho News — test AI API keys` on GitHub after commit.
- Actual AI article generation, provider quotas, feed reachability, GitHub Pages deployment and live article URLs require a live run. The preflight workflow validates keys/model discovery only; it does not prove generation quality.
- Free-tier quotas and model availability can change. If no explicitly free model is available, the pipeline reports a failure instead of selecting a paid model.
- To ensure zero charges, keep provider projects/accounts on free-tier billing and do not enable paid billing for the API projects. API keys alone cannot prove the account's billing tier.
