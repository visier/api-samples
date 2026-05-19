#!/usr/bin/env python3
"""
CLI: load ``config.yaml`` and run a guarded SDLC promotion sample.

Usage (from this directory)::

    pip install -r requirements.txt
    source .venv/bin/activate   # if you use a virtual environment
    python promote.py                  # preview only; no target changes
    python promote.py --apply          # create/import target draft; do not publish
    python promote.py --apply --publish

Troubleshooting draft project **name** vs API: set ``VISIER_SDLC_DEBUG=1`` and run again;
look for log lines tagged ``[SDLC troubleshooting]``. Unset the variable when done.
"""

from __future__ import annotations

import argparse
import logging
import sys

from visier_sdlc import (
    NewDraftProject,
    PromotionRequest,
    VisierClient,
    get_profile,
    load_config,
    run_sdlc_promotion,
)
from visier_sdlc.exceptions import VisierSDLCError


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Visier SDLC promotion: export from the source tenant, import on the target tenant, "
            "and publish only when explicitly requested."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("latest", "all"),
        default="latest",
        help=(
            "What to export from the source tenant's published history: "
            "'latest' = only the most recent published version; "
            "'all' = full version history in one export (paginated list, oldest→newest range)."
        ),
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        metavar="PATH",
        help="Path to config YAML (default: config.yaml).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply target changes: export the ZIP, create a target draft, and import commits. Does not publish.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Commit and publish the imported target draft. Requires --apply.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if args.publish and not args.apply:
        print("--publish requires --apply.", file=sys.stderr)
        return 1
    if args.dry_run:
        print(
            "--dry-run is deprecated and now behaves like the default preview mode. "
            "Use --apply to create/import a draft, or --apply --publish to publish.",
            file=sys.stderr,
        )

    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        print(
            f"Config not found: {args.config!r}\n"
            "Copy config.yaml.example to config.yaml and add credentials, "
            "or pass --config /path/to/config.yaml",
            file=sys.stderr,
        )
        return 1
    except (ImportError, KeyError, ValueError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    try:
        source = VisierClient(get_profile(cfg, "source"))
        target = VisierClient(get_profile(cfg, "target"))
    except (ImportError, KeyError, ValueError) as e:
        print(f"Setup error: {e}", file=sys.stderr)
        return 1

    full_history = args.mode == "all"
    # name/description are set in the workflow from source vanity + base URL (and, for
    # --mode latest, the exported version name and id) when auto_draft_naming is set.
    request = PromotionRequest(
        new_project=NewDraftProject(
            name="",
            description="",
            release_version="1",
            ticket_number="",
            version_number=0,
        ),
        export_full_published_history=full_history,
        auto_draft_naming=args.mode,
        apply_to_target=args.apply,
        publish=args.publish,
    )
    logging.info(
        "Mode: %s (full_published_history=%s, apply=%s, publish=%s)",
        args.mode,
        full_history,
        args.apply,
        args.publish,
    )

    try:
        result = run_sdlc_promotion(source, target, request)
    except VisierSDLCError as e:
        print(f"Aborted: {e}", file=sys.stderr)
        return 2

    print("Exported version ids:", result.export_start_version_id, result.export_end_version_id)
    print("Planned target draft name:", result.planned_project.name)
    print("Planned target draft description:", result.planned_project.description)
    if result.new_project is None:
        print("Preview only: no ZIP export, target draft creation, import, or publish was run.")
        return 0

    print("Export ZIP size bytes:", result.export_zip_size_bytes)
    print("Target draft id:", result.new_project.get("id"))
    print("Target draft name:", result.new_project.get("name"))
    if result.publish_result is not None:
        print("Publish (Step 5): completed.")
    else:
        print("Publish (Step 5): skipped. Inspect the target draft before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
