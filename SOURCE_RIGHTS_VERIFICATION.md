# AppNho News — source access and rights policy

The 50 RSS feeds are configured for metadata-only discovery. The pipeline retains headline, canonical URL and publication date; RSS descriptions and publisher full-text fields are not used as evidence.

The 228-row source directory is a research inventory, not a grant of crawling, copying or commercial reuse rights. The `terms_status`, `access_status` and `commercial_use_status` fields remain `UNVERIFIED` until a person reviews the relevant source terms.

## Two research modes

- `APPROVED_RESEARCH`: use only when `access_status=RESEARCH_ALLOWED` and `terms_status=VERIFIED`.
- `LIMITED_FACTUAL_REFERENCE`: operational fallback for public HTTPS pages when `NEWS_PUBLIC_FACTUAL_RESEARCH=1`, robots.txt allows the request, and the source is not explicitly marked `BLOCKED`. Only bounded page text is extracted temporarily to verify facts. The excerpt is not stored in the repository or republished. The resulting article must be independently written, link to the source, and set `reuse_mode=FACTUAL_CITATION_ONLY`.

`LIMITED_FACTUAL_REFERENCE` is not a statement that terms have been reviewed, that a source grants a commercial license, or that all automated access is legally permitted. If a source's terms or access policy are known to prohibit the intended access, set `terms_status=BLOCKED` or `access_status=BLOCKED`; the pipeline then refuses to fetch or publish from that source. Do not bypass login, paywall, CAPTCHA, HTTP 401/403, rate limits or other access controls.

## Commercial reuse

A commercial-use license is required for reused publisher text, photographs, video, graphics or other protected material. It is not treated as a prerequisite for independently written factual reporting that cites a source URL and does not reproduce its protected expression. Image assets are checked separately; only explicitly approved commercial licenses are accepted. No legacy image is automatically trusted during a content rewrite.

## Required source metadata

Keep these fields in `config/source_directory.csv`:
`source_family`, `access_status`, `terms_status`, `terms_url`, `robots_url`, `allowed_fields`, `commercial_use_status`, `rate_limit`, `quota`, `attribution_rule`, `last_checked`, `license_notes`, `claim_role`.

Never mark a source `VERIFIED` just because it has a public URL, RSS feed, robots.txt allowance, or government/university/research identity. Record the reviewer and date in the source notes when a human review is completed.
