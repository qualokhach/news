# AppNho News R6 — revised audit report (before commit)

## Changes in this revision
- Added per-feed publication-time windows in `scripts/news_pipeline.py`.
- Each enabled feed reads its own `feed_cursors` timestamp. Candidate publication time must satisfy `cursor < published_at <= run_started_at`.
- Default first-run boundary for this repository: `2026-10-24T06:00:00+07:00` (Vietnam time). Set the `NEWS_INITIAL_WINDOW_START` environment variable to override it before the first run.
- Missing/invalid source publication timestamps are skipped with an explicit log; they are not counted as fresh.
- Successful feed fetch + XML parse advances only that feed's cursor. A failed feed retains its prior cursor, allowing catch-up on a later run.
- Cursor state and pending leads are persisted together in `data/seen_items.json` and `data/pending.json` at the end of the pipeline. A workflow failure before the script writes state does not persist a new cursor.
- Added boundary tests to ensure the start is exclusive and the run-time upper bound inclusive.

## Local validation
- `python -m py_compile scripts/*.py`: PASS.
- `python scripts/test_pipeline_logic.py`: PASS (5 tests).
- Feed config JSON parses and configured URLs are unique: PASS.
- Workflow wiring reviewed: feed audit, AI pipeline, archive rotation, metadata rebuild, and commit step.

## Limitations and deployment verification
- This environment has no outbound internet access, so live HTTP/XML status of all configured feeds cannot be confirmed here. GitHub Actions must run `scripts/audit_feeds.py` and the report `data/feed_health.json` must be inspected.
- Unit tests cover window boundaries but do not prove real-world RSS timestamps are accurate. Sources that omit or misstate publication timestamps will be skipped or may require source-specific parser adjustments.
- The first-run bootstrap defaults to the user's stated example boundary (2026-10-24 06:00 Vietnam time). Confirm this is the desired initial boundary if the actual last successfully completed publication window differs.
- The pipeline does not promise that every discovered item will be published: deduplication, evidence checks, AI quality validation, and the per-run article cap still apply.
