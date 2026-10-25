# AppNho News — Master Routing (GitHub-only)

## Canonical decisions
- Canonical repository: `qualokhach/news`.
- Immutable historical archive: `data/archive_articles.json` (43 legacy articles).
- Active/new article file: `data/articles.json`; automation appends only new articles here.
- Queue: `data/pending.json`.
- Deduplication state: `data/seen_items.json` (bounded to the 20,000 most recent records).
- Public article URL format: `https://appnho.io.vn/news/article.html?id=<id>`.
- RSS: `https://appnho.io.vn/news/feed.xml`.
- Sitemap: `https://appnho.io.vn/news/sitemap.xml`.
- No Cloudflare R2, Worker, D1, storage API URL, or admin token is required for News in this release.

## Workflows
1. `build-news.yml`: scheduled 06:00 and 17:00 Vietnam-time target, collect RSS leads, deduplicate, draft only when API keys and evidence are available, validate, update JSON, rebuild RSS/sitemap, and commit changed data.
2. `manual-publish.yml`: manual workflow dispatch; validates a manually supplied article, auto-generates a unique ID, appends to the same article archive, rebuilds RSS/sitemap, and commits.

## Secrets
Optional repository Actions secrets: `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, `OPENROUTER_API_APPNHO_NEWS`. Do not store any API key in frontend code or JSON files. If no key is configured, automatic workflow does not generate articles.

## Data integrity and safety
- Preserve all existing article IDs during deployment.
- Never replace `data/articles.json` with an empty file.
- Do not use broad git add of unknown local files in workflow; workflow stages only expected data/metadata files.
- Workflow permissions are `contents: write` for committing updates. It does not need a personal access token.
- Article IDs are used in the existing query-string URL format; do not switch to slug paths without a separate migration.
- The repository and Git history grow with article updates. Monitor repository and published-site size.
- This is not yet verified on the user's real GitHub/Vercel account; run end-to-end tests before enabling scheduled operation.


GitHub Repository Secrets names used by this setup: `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, and `OPENROUTER_API_APPNHO_NEWS`. The workflow maps these to runtime environment variables `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY` respectively.
