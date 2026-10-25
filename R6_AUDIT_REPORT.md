# AppNho News R6 — corrective audit report

## Issue observed in GitHub Actions
Run #11 completed collection, article pipeline, archive rotation, and sitemap/RSS rebuild steps, then failed at `Commit updated articles and state` with:
`fatal: pathspec 'data/archive_batches' did not match any files`.

## Corrections applied
1. Workflow commit now stages `data/`, `sitemap.xml`, and `feed.xml` recursively. The commit no longer fails just because an optional archive batch directory has no files.
2. First-run per-feed cursor initialization now updates the persisted `feed_cursors` dictionary correctly.
3. Publication-time window stays strict: `cursor < source_published_at <= run_started_at`. Missing/invalid publication dates are skipped with a diagnostic.
4. Source diversity is tracked across successful publications in `data/seen_items.json` under `source_usage`, bounded to 200 recent records. Recent use lowers a source's selection score by a capped penalty; freshness and cross-source corroboration remain in scoring.
5. Source usage history is recorded only after a validated article is appended successfully, not for failed or rejected generations.
6. Added tests for the source diversity scoring penalty.

## Local tests
- `python -m py_compile scripts/news_pipeline.py scripts/audit_feeds.py scripts/rotate_archive.py scripts/build_metadata.py scripts/test_pipeline_logic.py`: PASS.
- `python scripts/test_pipeline_logic.py`: PASS, 7 tests.
- Workflow YAML parse: PASS.
- 50 configured feed URLs are unique and the JSON parses: PASS.
- ZIP archive integrity: PASS.

## Limitations
This is local/static validation. Live feed health and API-based article generation cannot be claimed until the revised workflow runs in GitHub Actions with the repository's configured secrets. Feed endpoints may still fail individually; `data/feed_health.json` records these results and the pipeline should continue past individual feed failures.

## Deployment note
This package is a full repository snapshot. Preserve newer article/archive data if any data was created after the snapshot was built; do not overwrite newer production data with older JSON. GitHub Secrets are repository settings and are not included in ZIP files.
