# AppNho News — GitHub-only archive and editorial upgrades (v1.5)

## Data policy
- `data/articles.json` contains the active article records.
- `data/archive_articles.json` contains the initial 43 archived article records.
- `data/archive_catalog.json` is a metadata index; `data/archive_manifest.json` and `data/archive_batches/` identify later archive files.
- Article IDs, slugs and public URLs remain stable during content upgrades.
- Archive batches are not rewritten by ordinary publication/rotation. The explicit v1.5 legacy-upgrade workflow may update article bodies and quality metadata in any manifest/catalog archive file when fresh evidence supports a rewrite. This exception is required to improve previously published content.
- `scripts/rotate_archive.py` closes active batches based on AppNho publication date, not the original event/source date.

## Date semantics
- `published_at`: date/time of the event or original source publication.
- `appnho_published_at`: date/time AppNho first published the article.
- `updated_at`: date/time of a substantive AppNho content update.
These fields must not overwrite one another. Structured data and site sorting use the AppNho publication date; event/source dates remain visible where useful.

## Content migration
`scripts/upgrade_legacy_articles.py`:
- Reads active articles and every archive file referenced by manifest/catalog.
- Uses old article text only to identify the topic; it is not accepted as evidence.
- Fetches source material and searches for matching official sources through the source directory.
- Rewrites only when the new fact ledger, source independence and v1.5 QA pass.
- Preserves IDs, slugs, collection, original event/source date and original AppNho publication date.
- Records automatic HOLD and retry timing when evidence is insufficient; it never waits for GitHub approval.

## Archive rotation
Once the oldest active AppNho publication reaches 30 days, `scripts/rotate_archive.py` closes the active batch into `data/archive_batches/`, updates catalog/manifest and clears the active batch. A later explicit editorial upgrade may still update the body of an archived article while preserving its URL and historical dates.
