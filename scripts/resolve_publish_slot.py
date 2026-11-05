#!/usr/bin/env python3
"""Resolve GitHub Actions event data into a publication slot without cron-string ambiguity."""
import os
import sys

NOON_CRON = "45 4 * * *"
REGULAR_CRONS = {"45 22 * * *", "45 9 * * *"}

def resolve_slot(event_name: str, event_schedule: str = "", dispatch_slot_kind: str = "") -> dict:
    if event_name == "schedule":
        if event_schedule == NOON_CRON:
            kind = "digest"
        elif event_schedule in REGULAR_CRONS:
            kind = "regular"
        else:
            raise ValueError(f"Unknown publication schedule event: {event_schedule!r}")
    elif event_name == "workflow_dispatch":
        kind = (dispatch_slot_kind or "regular").strip().lower()
        if kind not in {"regular", "digest"}:
            raise ValueError(f"Unsupported manual slot kind: {kind!r}")
    else:
        raise ValueError(f"Unsupported event type: {event_name!r}")
    # The noon slot also publishes up to 4 NEW articles (researched, written and gated like every
    # other slot); the digest is then built from the newest AppNho articles, with older ones used
    # only when fewer than 6 recent articles exist.
    return {"slot_kind": kind, "max_articles": "4"}

def main():
    result = resolve_slot(
        os.getenv("EVENT_NAME", ""),
        os.getenv("EVENT_SCHEDULE", ""),
        os.getenv("DISPATCH_SLOT_KIND", "")
    )
    for key, value in result.items():
        print(f"{key}={value}")

if __name__ == "__main__":
    main()
