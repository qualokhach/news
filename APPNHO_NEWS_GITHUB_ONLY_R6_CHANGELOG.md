# AppNho News R6 — corrective revision after GitHub Actions run #11

## Fixes
- Fixed the workflow commit step to stage `data/` recursively. It no longer names `data/archive_batches` as a required pathspec, so an absent/empty batch directory does not fail the entire run with Git exit code 128.
- Fixed first-run cursor initialization so per-feed cursors are stored in `seen_items.json` instead of a detached temporary dictionary.
- Kept strict publication-time windowing: each feed candidate must satisfy `cursor < source_published_at <= run_started_at`. Missing/invalid publication dates are skipped explicitly.
- Added cross-run source diversity. Successfully published source usage is stored in `seen_items.json` (`source_usage`, bounded to the last 200 records). Source scoring applies a bounded penalty to publishers used recently, while publication freshness and corroboration remain part of ranking.
- Diversity state advances only when an article is successfully published; failed/rejected candidates do not count as successful source usage.
- Added offline tests for source-use penalty and penalty bounds.

## Validation performed locally
- Python syntax compilation: PASS.
- Pipeline unit tests: PASS (7 tests).
- Workflow YAML parsed successfully with PyYAML.
- Feed configuration parses and contains unique URLs (50 configured feeds).
- ZIP integrity check: PASS.

## Not verified locally
- Live availability of all 50 feeds, because this environment cannot make outbound HTTP requests.
- Real API generation/publication using the repository's secrets. This must be verified by a GitHub Actions run.
