# Planning Events

This is a sample script that polls a plan for recent promotion events and loads data into the promoted rows.

The script:
1. Lists the promotion events of the last few minutes for a plan using the [Plan Events API](https://docs.visier.com/developer/apis/references/api-reference.htm#tag/PlanEvents). The bulk listing returns event summaries only.
2. Fetches the full detail of each event to obtain the promoted member paths.
3. Fetches the plan's schema to determine which dimensions and time periods to populate.
4. Builds a CSV per scenario with value `1` for the configured plan item across all promoted rows and time periods.
5. Validates and uploads each CSV using the [Plan Data Load API](https://docs.visier.com/developer/apis/references/api-reference.htm#tag/PlanDataLoad).

This polling approach is an alternative to reacting to a `planRowPromotionNotification` webhook. Run it on a schedule with `LOOKBACK_MINUTES` matched to the interval.

The following promotion event types are supported: `memberPromoted`, `autoPromotion`, and `bulkPromotionDemotionEvent`.

## Getting Started

### Environment
Python 3.x installed on your system with the following dependencies:
- `python-dotenv==1.1.1`
- `visier-platform-sdk==22222222.99201.2909`

You can install them using pip and the provided `requirements.txt`:
```bash
pip install -r requirements.txt
```

## Configuration
Configure the `.env` file with the following environment variables. You can use `.env.example` as a starting point:
```bash
cp .env.example .env
```

### Authentication
This script authenticates using the [Visier Python SDKs](https://github.com/visier/python-sdk). For more authentication options, see [API Authentication](https://docs.visier.com/visier-people/Default.htm#cshid=1054).
```env
VISIER_HOST=https://customer-specific.api.visier.io
VISIER_APIKEY=visier-provided-api-key
VISIER_USERNAME=visier-username
VISIER_PASSWORD=visier-password
VISIER_VANITY=visier-tenant-vanity-name
```

### Script Configuration
```env
PLAN_ID=your-plan-uuid-here
PLAN_ITEM_ID=your-plan-item-id-here
LOOKBACK_MINUTES=5
MAX_EVENTS=10
```

- **`PLAN_ID`** (required): The UUID of the plan to poll for promotion events. The user must have View access to the plan, and full access to all rows in the plan tree.
- **`LOOKBACK_MINUTES`** (optional, default `5`): How far back to look for promotion events. The script converts this to the `fromDate` query parameter, which is an exclusive filter in epoch milliseconds.
- **`MAX_EVENTS`** (optional, default `10`): The maximum number of events to process. If the window contains more, only the most recent `MAX_EVENTS` are processed, which bounds the number of detail requests the script makes.
- **`PLAN_ITEM_ID`** (required): The ID of the plan item to populate with data, for example `Headcount_And_Cost_Planning.Headcount`. To get the plan item ID, call `GET /v1alpha/planning/model/plans/{id}?withSchema=true`.

## Usage

Run the script with:
```bash
python main.py
```

### What the Script Does

1. **List events**: Calls `GET /v1/planning/data/events` filtered by `planId`, `fromDate`, and the three promotion event types. Results are sorted oldest first and returned in pages of up to 50, which the script pages through using `start`. It then keeps only the most recent `MAX_EVENTS` summaries.
2. **Fetch event details**: The bulk listing returns summaries without promoted rows, so the script calls `GET /v1/planning/data/events/{eventId}` for each of the retained events. Promoted rows are grouped by scenario and deduplicated, because the same row can be promoted by more than one event in the window.
3. **Fetch plan schema**: Retrieves the plan's segment levels (dimensions), time periods, and scenario information.
4. **Build CSV**: Generates `event_upload_<scenarioId>.csv` per scenario, with one row per promoted row and time period combination. The value `1` is written to the configured plan item for every cell. Dimension columns not covered by a promoted row are left empty, which the API interprets as applying across all values for that dimension.
5. **Validate and upload**: For each scenario, runs a dry-run validation first. If no errors are found, uploads the CSV using `STRICT_UPLOAD`. If validation fails, the errors are printed and that upload is skipped.

### Error Handling
- **Plan not found (404)**: The plan does not exist, the user does not have View access, or the user does not have full access to all rows in the plan. The server returns 404 in all these cases to avoid leaking whether the plan exists. The script stops.
- **Event not readable**: If an individual event cannot be fetched or is of an unsupported type, it is skipped with a message and the remaining events are still processed.
- **No edit rights (403)**: The user does not have edit rights to the plan or scenario and cannot upload data.
