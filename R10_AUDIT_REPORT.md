# AppNho News R10 — audit report

## Changes
- Category pages now keep the branded homepage hero, with category-specific title, description and chips.
- Category pages add bottom navigation to the other three categories, the homepage and the history/archive section.
- Collect/write/publish workflow runs when pipeline code or feed configuration changes, as well as on its existing schedule and manual dispatch. Path filters prevent bot data-only commits from triggering a repeat pipeline loop.
- GitHub Actions step summary reports enabled/successful feeds, new leads, configured AI-key count, AI attempts/responses, published count, feed failures and generation failures.
- Site audit now asserts the category hero and history/navigation link are present.

## Local validation results
- `node --check assets/app.js`: PASS.
- `node --check assets/article.js`: PASS.
- `python -m py_compile scripts/*.py`: PASS.
- `python -m unittest discover -s scripts -p 'test_*.py' -v`: PASS, 7/7 tests.
- `python scripts/audit_site.py`: PASS; active=3, archived=43, catalog=43, pending=122, categories=4/4.
- JSON parse: PASS for all JSON files.
- YAML parse: PASS for all 3 GitHub workflows.
- `python scripts/build_metadata.py`: PASS; generated sitemap with 48 URLs and RSS with 46 articles.
- ZIP integrity: PASS.

## Important: live article generation
The package does not have access to the user's GitHub Secrets and cannot prove that a provider accepts the configured keys from this environment. An attempted live feed audit exceeded the sandbox time limit, so external RSS availability is **not confirmed here**. R10's workflow is path-triggered on a code/config commit and will write a per-run summary in GitHub Actions. That summary will distinguish: no fresh leads, failed feeds, missing AI keys, provider/model errors, rejected stories and successful publication. Zero articles in one run is not automatically proof of a code defect; repeated runs must be diagnosed from these counters and logs.

## Data safety
- Article datasets were not fabricated or reset.
- `data/articles.json`: 3 active articles.
- `data/archive_articles.json`: 43 full archived articles.
- `data/archive_catalog.json`: 43 catalog records.
- `data/pending.json`: 122 items awaiting editorial/rights review or processing; not automatically published.
