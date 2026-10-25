# AppNho News R6 changelog — revised before commit

- Expanded the feed configuration to 50 unique sources across Vietnam, world, technology, and sports.
- Added a live RSS/Atom health audit that logs HTTP status, parse result, and item count per source.
- Added `data/feed_health.json` to the pipeline commit output.
- **Fixed time-window selection:** each feed has its own durable `feed_cursors` checkpoint. New leads are eligible only when the source publication time is strictly after that feed's cursor and no later than the run start time.
- First-run bootstrap boundary is `2026-10-24T06:00:00+07:00` by default for this repository; override with `NEWS_INITIAL_WINDOW_START` if a different initial boundary is required.
- A source with missing/invalid publication time is not treated as new. It is logged and skipped rather than silently considered fresh.
- A feed's cursor advances only after successful HTTP fetch and RSS/Atom parsing. If a feed fails, its previous cursor is retained so a later run can catch up.
- The cursor and discovered leads are written together by the same pipeline execution; if the script fails before persistence, the updated cursor is not committed.
- Added unit tests for exclusive lower boundary, inclusive run-time upper boundary, and missing/invalid dates.
- Kept existing article/archive files and 30-day rotation behavior unchanged.

## Validation
- Python syntax compilation: PASS.
- Pipeline logic tests: PASS (5 tests).
- JSON source configuration and unique URL checks: performed locally.
- Live feed availability still requires a GitHub Actions run; this build environment has no outbound internet access.
