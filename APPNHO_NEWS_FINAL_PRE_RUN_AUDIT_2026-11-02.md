# AppNho News — final pre-run audit (02/11/2026)

## Purpose

This patch consolidates the previously prepared event/evidence filtering, full provider fallback validation, Cloudflare response handling, and editorial length policy. It is intended to reduce wasted model calls and prevent a draft from being discarded after one provider's output fails a downstream quality check.

## Main behavior

1. Research remains API-free. RSS is discovery metadata only; evidence pages and independent sources are collected before writing.
2. Candidate evidence is filtered against the lead event before any model call. Unrelated source headlines/pages are removed. Candidates that no longer have two independent source families or a suitable primary source are held without spending AI calls.
3. Providers are tried in order: Gemini, Cloudflare Workers AI (`@cf/meta/llama-3.3-70b-instruct-fp8-fast`), then explicitly free OpenRouter models.
4. A provider is accepted only after the complete local article validation callback succeeds, including fact ledger verification, source independence, risk rules, plagiarism/similarity check, and article quality. A provider draft that fails these checks falls through to the next provider; the research brief/evidence is reused.
5. Cloudflare response parsing handles supported string and structured-object forms.
6. Editorial length targets are guidance, not pass/fail targets. Minimum safety floors by content type are 120/220/420/550 words; paragraph floors are 2/3/4/5. The full content quality gate applies the same floors. Evidence, factual accuracy, originality, and editorial value remain mandatory.
7. Technical writing failures are delayed and bounded: one retry window after 6 hours; after two failed sessions the candidate is held for manual review. This prevents endless paid/free API retries on every scheduled run.

## Current queue audit

From the submitted ZIP:
- 13 research queue entries: 9 HOLD and 4 WRITING_PENDING.
- After title/evidence relevance filtering, the four staged candidates currently resolve as:
  - Ciara Mageean: 3 relevant sources / 3 independent source families; eligible for a writing attempt.
  - J-PAL ARTEMIS: 1 relevant source; HOLD without AI call.
  - Peanut research item: 1 relevant source; HOLD without AI call.
  - Olympia winner item: 2 relevant sources / 2 independent source families; eligible for a writing attempt.

Eligibility for writing is not a guarantee of publication. Both candidates still have to pass live source checks and the final publish gate.

## Offline verification performed on the consolidated working tree

- `python -m unittest discover -s scripts -p 'test_*.py'`: 103/103 PASS.
- Python compile: all scripts compile.
- Workflow YAML parse: 6/6 PASS.
- `python scripts/audit_site.py`: PASS.
- Local/external link audit: 270 anchors checked.
- Site data: 77 active articles, 43 archived articles, 43 archive catalog entries, 5,000 pending leads, 13 research queue entries.
- No live AI provider calls were made during this audit.

## Operational limits

This audit cannot guarantee that a particular article will be published: provider quotas, GitHub Actions scheduling, live publisher availability, source freshness, and factual sufficiency are external conditions. The system should publish only when the candidate passes all checks. The design goal is to keep enough qualified candidates in the queue and to avoid losing a researched candidate because one model's output failed a downstream gate.
