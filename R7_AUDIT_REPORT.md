# AppNho News R7 — Audit report

## Source snapshots used
- Backup 1: `news-main backup 1 - trước khi commit R5.zip`
- Backup 2: `news-main backup 2 - trước khi commit R6 corrected.zip`
- Code overlay: R6 Corrected full package previously prepared in this conversation.

## Data preservation decisions
- Active articles: retained the 3 articles from backup 2 (`data/articles.json`).
- Historical archive: retained all 43 archived articles from backup 2 (`data/archive_articles.json`) and its 43-entry catalog.
- Editorial queue: restored 122 pending discovery items from backup 1 because backup 2 had an empty queue (`[]`). These are discovery leads marked `needs_editorial_and_rights_review`, not published articles.
- `seen_items.json`: retained the state from backup 2; it was empty and contained no last-run cursor/stats.
- `archive_manifest.json`: retained archive pointer to `data/archive_articles.json`.
- Code/workflow files: overlaid from the R6 Corrected package while retaining files unique to backup 2. Python cache files removed.

## Checks performed
- All JSON files parse.
- All Python files compile.
- `scripts/test_pipeline_logic.py`: 7 tests passed (source diversity, time window boundaries, missing/invalid dates, and provider model filtering).
- Active article IDs and archive article IDs do not overlap.
- ZIP structure checked after packaging.

## Important limitations
- This is a local audit only. RSS endpoints, provider API calls, GitHub Actions execution, and deployed website rendering have not been live-tested in the user's GitHub environment.
- The 122 pending items are retained as leads for review; they are not promoted automatically to published articles by this merge.
- GitHub Secrets are not included in ZIP and should remain configured in repository settings.
