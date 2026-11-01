# AppNho News — Master Routing v1.5

## Canonical decisions
- Canonical repository: `qualokhach/news`.
- Current articles: `data/articles.json`.
- Initial historical archive: `data/archive_articles.json`.
- Later archive batches: `data/archive_batches/`, indexed by `data/archive_catalog.json` and `data/archive_manifest.json`.
- Discovery queue: `data/pending.json`.
- Researched candidates ready for publication: `data/research_queue.json`.
- Deduplication and feed cursors: `data/seen_items.json`.
- Source index: `config/source_directory.csv` (228 source entries; not a pre-approved license list).
- Public article URL: `https://appnho.io.vn/news/article.html?id=<id>`.
- RSS: `https://appnho.io.vn/news/feed.xml`.
- Sitemap: `https://appnho.io.vn/news/sitemap.xml`.
- No Cloudflare R2, Worker, D1 or storage API is required.

## Workflows
1. `research-news.yml`: discover events, group duplicates, collect evidence, build fact ledger, create a draft and place PASS candidates in `research_queue.json`. It does not publish.
2. `build-news.yml`: run final checks 15 minutes before each Vietnam publication slot, publish only ready candidates, rebuild metadata and commit.
3. `legacy-upgrade.yml`: revisit current and archived published articles in small batches and rewrite only when new evidence supports a v1.5-compliant version.
4. `validate-news.yml`: test code/data on push and pull request; it does not publish.
5. `manual-publish.yml`: legacy name; stages a user-submitted research lead only. It does not append directly to published articles.
6. `test-ai-apis.yml`: preflight for Gemini, Grok/xAI and OpenRouter.

## Schedule
- Research: `0 2,7,14,20 * * *` UTC.
- Finalization: `45 22,4,9 * * *` UTC, corresponding to 05:45, 11:45 and 16:45 Vietnam time.
- Legacy content upgrade: `30 5,11,17,23 * * *` UTC.

## Secrets
- `GEMINI_API_KEY_APPNHO_NEWS` → `GEMINI_API_KEY`.
- `GROK_API_APPNHO_NEWS` → `XAI_API_KEY`.
- `OPENROUTER_API_APPNHO_NEWS` → `OPENROUTER_API_KEY`.
Do not use Groq; the configured secondary provider is Grok/xAI.

## Date and archive integrity
- `published_at` is the event/source date.
- `appnho_published_at` is AppNho's publication date.
- `updated_at` is a substantive content update date.
- Content upgrades preserve IDs, slugs and historical dates. The legacy-upgrade workflow may update old archive bodies; ordinary rotation does not rewrite closed archive batches.
- Byline is `AppNho`; no fictional authors or editorial staff are created.

## Safety
- Do not store API keys in frontend files or JSON.
- Do not bypass paywalls, CAPTCHA, login or HTTP 401/403 blocks.
- `robots.txt` is not a copyright license. The source directory is a discovery/research index, not proof of commercial reuse permission.
- If no candidate passes quality and freshness checks, log `missed_slot`; never lower the threshold to fill a schedule.
