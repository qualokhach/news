# AppNho News GitHub-only R4 — changelog and verification

## Requested changes
- Keep the original 43 articles in `data/archive_articles.json` as the initial immutable archive batch; existing IDs are preserved.
- Backfill the missing dates 23, 24 and 25 October 2026 with three Vietnamese daily briefing articles, each 600+ words, and primary/secondary source links.
- Keep new stories in `data/articles.json` as the active batch.
- After the active batch's oldest article reaches 30 days, close the entire active batch into `data/archive_batches/articles-<start>-to-<end>.json`. The script refuses to overwrite an existing closed batch.
- Add `data/archive_catalog.json` as a metadata-only catalog and `data/archive_manifest.json` as the list of closed data files. The catalog/manifest change only when a batch closes, not on each normal publication.
- The homepage loads active content, the initial archive, and archived metadata. Article detail fetches a closed monthly batch only when opening an article in that batch.
- Automatic and manual workflows run the rotation script before rebuilding RSS and sitemap, and commit all needed data/metadata files.
- RSS includes up to the 100 latest articles; sitemap contains all article IDs known to the catalog and current data.

## Backfilled content note
These are three daily roundup articles, one for each requested date. They are not 24 individually reported stories. Their factual points are paraphrased and attributed to public news sources; the article page lists the primary and supplementary source links. The 25 October roundup relies on reporting published by that date and labels forecasts/ongoing developments as such.

## Local verification performed
- Python compile check passed for all scripts.
- JavaScript syntax checks passed for `assets/app.js` and `assets/article.js`.
- JSON parsing passed for archive, current articles, catalog and manifest.
- XML parsing passed for `feed.xml` and `sitemap.xml` after regeneration.
- Verified 43 original archive entries remain; 3 backfilled entries cover 2026-10-23, 2026-10-24 and 2026-10-25; IDs are unique across the original archive and active batch.
- Verified archive catalog initially maps 43 metadata entries to `data/archive_articles.json`.
- Ran rotation in a separate test copy with article dates older than 30 days: 3 entries moved to a new batch, active file cleared, catalog and manifest updated, and the closed file created without overwrite.
- Normal local rotation run on the package did not close the new active batch because it is only 1 day old.

## Not verified
- No real GitHub Actions workflow was executed against the user's repository.
- No live production deployment or browser end-to-end test was performed.
- Actual article URLs should be checked after uploading and deploying the ZIP.

## R4-specific change
- Updated `.github/workflows/build-news.yml` to map the repository secrets `GEMINI_API_KEY_APPNHO_NEWS`, `GROK_API_APPNHO_NEWS`, and `OPENROUTER_API_APPNHO_NEWS` to the environment variables consumed by the pipeline: `GEMINI_API_KEY`, `GROQ_API_KEY`, and `OPENROUTER_API_KEY`.

## Deployment cautions
Back up `qualokhach/news` before replacing files. Do not enable scheduled publication until old article links and all three backfilled articles are checked on the deployed site. GitHub Actions must retain `contents: write` permissions. AI API secrets must be configured in repository Actions secrets for automated drafting; without them, the current pipeline only discovers sources and will not publish automatically.
