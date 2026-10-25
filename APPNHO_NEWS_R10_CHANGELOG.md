# AppNho News R10 — changelog

## Category page UX
- Category indexes retain the branded homepage hero artwork.
- Hero title, description and pills adapt to the selected category.
- Category index keeps the filtered news list and adds a bottom "Khám phá thêm" area linking to the other three categories, the homepage and the archive/history section.
- Homepage category tiles and homepage-only category/archive sections remain hidden while a category is selected, so the page stays focused.

## Automation observability
- The collect/write/publish workflow now runs on pushes that change pipeline code, workflow configuration or feed configuration, in addition to manual and scheduled runs.
- The push trigger is path-limited to code/configuration, so bot commits that only update data/RSS/sitemap do not trigger a loop.
- Each run writes a step summary with feed health, new leads, AI attempts/responses, published count and failure counts.
- Site audit checks that category hero and onward-navigation features are present.

## Data safety
- No article, archive, pending, seen-state or feed configuration data was fabricated or reset by this UI revision.
- Existing archive and editorial review rules remain in place.
