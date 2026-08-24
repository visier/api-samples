import csv
import os
import sys
import time

from dotenv import load_dotenv
from visier_platform_sdk import (
    ApiClient,
    Configuration,
    DataModelApi,
    PlanDataLoadApi,
    PlanEventsApi,
    PlanningEventResponse,
    PromotedRowDTO,
)
from visier_platform_sdk.exceptions import ApiException, BadRequestException, ForbiddenException, NotFoundException

load_dotenv()

PLAN_ID = os.getenv("PLAN_ID")
PLAN_ITEM_ID = os.getenv("PLAN_ITEM_ID")
LOOKBACK_MINUTES = int(os.getenv("LOOKBACK_MINUTES", "5"))
MAX_EVENTS = int(os.getenv("MAX_EVENTS", "10"))

# The promotion event types this sample knows how to turn into upload rows.
PROMOTION_EVENT_TYPES = ["memberPromoted", "autoPromotion", "bulkPromotionDemotionEvent"]

# The server clamps the page size to its own maximum, which is 50 by default.
PAGE_SIZE = 50

config = Configuration.from_env()
api_client = ApiClient(config)
events_api = PlanEventsApi(api_client)
data_model_api = DataModelApi(api_client)
plan_data_load_api = PlanDataLoadApi(api_client)


def find_recent_promotion_events(plan_id: str, lookback_minutes: int, max_events: int) -> list:
    """
    Lists promotion event summaries for a plan within the lookback window using the
    bulk events endpoint.

    `fromDate` is an exclusive filter expressed as epoch milliseconds in a string.
    Results are sorted oldest first, so paging forward with `start` is stable.
    The summaries do not include promoted rows; the caller fetches those per event.

    Returns at most `max_events` summaries, the most recent ones. Because the API
    sorts oldest first and reports no total count, the most recent events are the
    tail of the result, so the window has to be paged to its end before trimming.
    Listing is one call per 50 events, which keeps the cost low; the trimming exists
    to bound the expensive part, the per-event detail calls that follow.
    """
    from_date = str(int((time.time() - lookback_minutes * 60) * 1000))

    summaries = []
    start = 0
    while True:
        response = events_api.get_events(
            plan_id=plan_id,
            from_date=from_date,
            event_types=PROMOTION_EVENT_TYPES,
            limit=PAGE_SIZE,
            start=start,
        )
        page = response.events or []
        summaries.extend(page)
        # A short page means there is nothing left; the response carries no total count.
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    if len(summaries) > max_events:
        print(f"Found {len(summaries)} events; processing the {max_events} most recent.")
        return summaries[-max_events:]
    return summaries


def get_promoted_rows(event: PlanningEventResponse) -> list[PromotedRowDTO]:
    if event.event_type in ("memberPromoted", "autoPromotion"):
        return event.promotion_data.promoted_rows or []
    elif event.event_type == "bulkPromotionDemotionEvent":
        return event.bulk_promotion_demotion_data.promoted_rows or []
    else:
        raise ValueError(f"Unsupported event type: {event.event_type}")


def collect_promoted_rows(summaries: list) -> dict[str, list[PromotedRowDTO]]:
    """
    Fetches the full detail of each event summary and groups the promoted rows by
    scenario, since each scenario is uploaded separately.

    Events that cannot be read are skipped rather than aborting the batch: in a
    polling run, one inaccessible or unsupported event should not stop the rest.
    Rows are deduplicated per scenario because the same row can be promoted by
    more than one event within the window.
    """
    rows_by_scenario: dict[str, list[PromotedRowDTO]] = {}
    seen_by_scenario: dict[str, set] = {}

    for summary in summaries:
        event_id = summary.event_id
        try:
            event = events_api.get_event(event_id)
        except NotFoundException:
            print(f"  Skipping event {event_id}: not found or not accessible.")
            continue
        except ApiException as e:
            print(f"  Skipping event {event_id}: HTTP {e.status} - {e.reason}")
            continue

        try:
            promoted_rows = get_promoted_rows(event)
        except ValueError as e:
            print(f"  Skipping event {event_id}: {e}")
            continue

        scenario_id = event.scenario_id
        seen = seen_by_scenario.setdefault(scenario_id, set())
        rows = rows_by_scenario.setdefault(scenario_id, [])
        for promoted_row in promoted_rows:
            # A member path uniquely identifies a row within a plan.
            key = tuple((m.dimension_id, m.level_id, m.member_id) for m in (promoted_row.member_path or []))
            if key not in seen:
                seen.add(key)
                rows.append(promoted_row)

    return rows_by_scenario


def build_csv(promoted_rows: list[PromotedRowDTO], schema, plan_item_id: str, output_path: str) -> int:
    """
    Transforms promoted rows from a planning event into the CSV format required
    by the Planning Data Load API.

    For each promoted row x time period, one CSV row is produced. The promoted row's
    memberPath is mapped to segment level columns using "dimensionId.levelId" as the
    key. Segment levels absent from the member path are left empty, which the API
    interprets as aggregating across all values for that dimension.

    Returns the number of rows written.
    """
    # Segment level IDs are the dimension columns in the upload CSV, e.g. "Location.Location_2".
    # Each one represents a dimension and level that the plan is segmented by.
    segment_level_ids = [sl.id for sl in schema.plan_segment_levels]
    period_dates = [tp.var_date for tp in schema.time_periods]
    fieldnames = ["periodId"] + segment_level_ids + [plan_item_id]

    # Write one row per promoted row x time period combination.
    # Columns: periodId, one column per segment level (dimension), and the plan item value.
    row_count = 0
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for promoted_row in promoted_rows:
            dim_lookup = {
                f"{m.dimension_id}.{m.level_id}": m.member_id
                for m in (promoted_row.member_path or [])
            }
            for period_date in period_dates:
                row = {"periodId": period_date}
                for seg_id in segment_level_ids:
                    row[seg_id] = dim_lookup.get(seg_id, "")
                row[plan_item_id] = 1
                writer.writerow(row)
                row_count += 1

    return row_count


def validate_and_upload(plan_id: str, scenario_id: str, csv_path: str) -> None:
    with open(csv_path, "rb") as f:
        data = f.read()

    try:
        print("Validating CSV...")
        validation = plan_data_load_api.plan_data_upload(
            plan_id,
            scenario_id,
            calculation="NONE",
            method="VALIDATE",
            file=data,
        )
        if validation.errors:
            print(f"Validation failed with {len(validation.errors)} error(s). Upload aborted.")
            for err in validation.errors:
                print(f"  Row {err.row}: [{err.rci}] {err.error_message}")
            return

        print("Validation passed. Uploading...")
        result = plan_data_load_api.plan_data_upload(
            plan_id,
            scenario_id,
            calculation="NONE",
            method="STRICT_UPLOAD",
            file=data,
        )
        print(f"Upload successful. Updated {result.updated_cells_count} cells.")
    except ForbiddenException:
        print("Upload failed: you do not have edit rights on this plan or scenario.")
    except ApiException as e:
        print(f"Upload failed: HTTP {e.status} - {e.reason}")


def main() -> None:
    if not PLAN_ID:
        print("PLAN_ID is required. Set it in your .env file.")
        sys.exit(1)
    if not PLAN_ITEM_ID:
        print("PLAN_ITEM_ID is required. Set it in your .env file.")
        sys.exit(1)

    print(f"Looking for promotion events on plan {PLAN_ID} in the last {LOOKBACK_MINUTES} minute(s)...")
    try:
        summaries = find_recent_promotion_events(PLAN_ID, LOOKBACK_MINUTES, MAX_EVENTS)
    except NotFoundException:
        # The server returns 404 for both unknown and inaccessible plans,
        # to avoid leaking whether the plan exists.
        print(f"Plan '{PLAN_ID}' was not found. Possible reasons:")
        print("  - The plan ID does not exist.")
        print("  - You do not have the VIEW right on the plan.")
        print("  - You do not have full access to all rows in the plan tree.")
        return
    except ApiException as e:
        print(f"Failed to list events for plan '{PLAN_ID}': HTTP {e.status} - {e.reason}")
        return

    if not summaries:
        print("No promotion events in the lookback window. Nothing to upload.")
        return
    print(f"Found {len(summaries)} promotion event(s). Fetching details...")

    rows_by_scenario = collect_promoted_rows(summaries)
    if not rows_by_scenario:
        print("None of the events contained promoted rows. Nothing to upload.")
        return

    print(f"Fetching plan schema for {PLAN_ID}...")
    schema_response = data_model_api.plan_info_with_schema(id=PLAN_ID, with_schema=True)
    schema = schema_response.var_schema
    default_scenario_id = schema_response.plan.scenarios[0].uuid

    # Each scenario is a separate upload, so it gets its own CSV.
    for scenario_id, promoted_rows in rows_by_scenario.items():
        effective_scenario_id = scenario_id or default_scenario_id
        if not scenario_id:
            print(f"Events without a scenario; using first plan scenario: {effective_scenario_id}")

        output_csv = f"event_upload_{effective_scenario_id}.csv"
        row_count = build_csv(promoted_rows, schema, PLAN_ITEM_ID, output_csv)
        print(f"\nScenario {effective_scenario_id}: {len(promoted_rows)} promoted row(s)")
        print(f"CSV written to {output_csv} ({row_count} rows)")

        validate_and_upload(PLAN_ID, effective_scenario_id, output_csv)


if __name__ == "__main__":
    main()
