import csv
import os

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

EVENT_ID = os.getenv("EVENT_ID")
PLAN_ITEM_ID = os.getenv("PLAN_ITEM_ID")
OUTPUT_CSV = "event_upload.csv"

config = Configuration.from_env()
api_client = ApiClient(config)
events_api = PlanEventsApi(api_client)
data_model_api = DataModelApi()
plan_data_load_api = PlanDataLoadApi(api_client)


def get_promoted_rows(event: PlanningEventResponse) -> list[PromotedRowDTO]:
    if event.event_type in ("memberPromoted", "autoPromotion"):
        return event.promotion_data.promoted_rows or []
    elif event.event_type == "bulkPromotionDemotionEvent":
        return event.bulk_promotion_demotion_data.promoted_rows or []
    else:
        raise ValueError(f"Unsupported event type: {event.event_type}")


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
    print(f"Fetching event {EVENT_ID}...")
    try:
        event = events_api.get_event(EVENT_ID)
    except NotFoundException:
        # The server returns 404 for both missing events and insufficient access,
        # to avoid leaking whether the event exists at all.
        print(f"Event '{EVENT_ID}' was not found. Possible reasons:")
        print("  - The event ID does not exist.")
        print("  - You do not have the VIEW right on the plan.")
        print("  - You do not have full access to all rows in the plan tree.")
        return
    except BadRequestException as e:
        print(f"Bad request when fetching event '{EVENT_ID}': {e.body}")
        print("  The getEvent API only supports: memberPromoted, autoPromotion, bulkPromotionDemotionEvent.")
        return
    except ApiException as e:
        print(f"Failed to fetch event '{EVENT_ID}': HTTP {e.status} - {e.reason}")
        return

    plan_id = event.plan_id
    scenario_id = event.scenario_id
    event_type = event.event_type
    print(f"Event type: {event_type}, plan: {plan_id}")

    try:
        promoted_rows = get_promoted_rows(event)
    except ValueError as e:
        # This sample only handles promotion events: memberPromoted, autoPromotion, bulkPromotionDemotionEvent.
        print(f"Unsupported event: {e}")
        print("  This sample supports: memberPromoted, autoPromotion, bulkPromotionDemotionEvent.")
        return
    if not promoted_rows:
        print(f"Event '{EVENT_ID}' has no promoted rows. Nothing to upload.")
        return
    print(f"Found {len(promoted_rows)} promoted row(s)")

    print(f"Fetching plan schema for {plan_id}...")
    schema_response = data_model_api.plan_info_with_schema(id=plan_id, with_schema=True)
    schema = schema_response.var_schema

    if not scenario_id:
        scenario_id = schema_response.plan.scenarios[0].uuid
        print(f"No scenario in event; using first plan scenario: {scenario_id}")

    row_count = build_csv(promoted_rows, schema, PLAN_ITEM_ID, OUTPUT_CSV)
    print(f"CSV written to {OUTPUT_CSV} ({row_count} rows)")

    validate_and_upload(plan_id, scenario_id, OUTPUT_CSV)


if __name__ == "__main__":
    main()
