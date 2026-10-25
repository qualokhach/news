# AppNho News — GitHub-only archive batches (R5)

## Data policy
- `data/archive_articles.json` is the first immutable historical batch: the 43 articles available through 22/10/2026. IDs and URLs are preserved.
- `data/articles.json` is the active batch. It contains articles published after the initial archive and is the only full-content JSON file appended to during normal operation.
- `data/archive_catalog.json` is a lightweight metadata catalog for archived articles. It is updated only when a new batch closes (roughly every 30 days), not on every daily publication.
- `data/archive_manifest.json` lists closed article files. `data/archive_batches/articles-<start>-to-<end>.json` stores each later closed batch. Closed batch files are never overwritten.
- `scripts/rotate_archive.py` closes the entire active batch once its oldest article is at least 30 days old, marks those entries as archive, writes a new batch file, updates catalog/manifest, then clears the active JSON. It refuses to overwrite an existing batch.
- Both automatic and manual workflows run rotation before rebuilding RSS/sitemap.
- `feed.xml` lists up to 100 latest articles; `sitemap.xml` includes all known article IDs.
- Frontend loads only the current batch, the initial 43-item archive, and archived metadata. When a user opens an older article, it fetches only the relevant closed batch file.

## Backfilled dates
Three editorial daily briefings for 23, 24 and 25 October 2026 were added from cited public reporting. Each item contains source links in `source_links`; `source_url` points to its primary source. These are date-specific roundups, not eight separate stories per day.

## Checks before production
1. Verify old article IDs and URLs.
2. Verify the three backfilled article dates and source links.
3. Test article opening from `data/archive_articles.json`, active `data/articles.json`, and a simulated closed batch.
4. Test a rotation in a temporary copy; never overwrite closed batches.
5. Run GitHub Actions manually and inspect the commit before enabling the schedule.
