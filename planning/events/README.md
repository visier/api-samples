# Planning Events

This is a sample script that reads a planning promotion event and loads data into the promoted rows.

The script:
1. Fetches a planning event by ID using the [Plan Events API](https://docs.visier.com/developer/apis/references/api-reference.htm#tag/PlanEvents).
2. Fetches the plan's schema to determine which dimensions and time periods to populate.
3. Builds a CSV with value `1` for the configured plan item across all promoted rows and time periods.
4. Validates and uploads the CSV using the [Plan Data Load API](https://docs.visier.com/developer/apis/references/api-reference.htm#tag/PlanDataLoad).

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
EVENT_ID=your-event-uuid-here
PLAN_ITEM_ID=your-plan-item-id-here
```

- **`EVENT_ID`** (required): The UUID of the promotion event to process. The user must have View access to the plan the event belongs to. To get the event ID, use the [Webhook API](https://docs.visier.com/developer/apis/references/api-reference.htm#tag/Webhooks) to create a webhook for the `planRowPromotionNotification` event. When the webhook triggers, its payload returns the `eventID`.
- **`PLAN_ITEM_ID`** (required): The ID of the plan item to populate with data, for example `Headcount_And_Cost_Planning.Headcount`. To get the plan item ID, call `GET /v1alpha/planning/model/plans/{id}?withSchema=true`.

## Usage

Run the script with:
```bash
python main.py
```

### What the Script Does

1. **Fetch event**: Retrieves the event and extracts its promoted rows. Each promoted row represents a set of dimension members that was promoted.
2. **Fetch plan schema**: Retrieves the plan's segment levels (dimensions), time periods, and scenario information.
3. **Build CSV**: Generates `event_upload.csv` with one row per promoted row and time period combination. The value `1` is written to the configured plan item for every cell. Dimension columns not covered by a promoted row are left empty, which the API interprets as applying across all values for that dimension.
4. **Validate and upload**: Runs a dry-run validation first. If no errors are found, uploads the CSV using `STRICT_UPLOAD`. If validation fails, the errors are printed and the upload is skipped.

### Error Handling
- **Event not found (404)**: The event does not exist, the user does not have View access to the plan, or the user does not have full access to all rows in the plan. The server returns 404 in all these cases to avoid leaking whether the event exists.
- **Unsupported event type (400)**: The event type is not supported by the Plan Events API.
- **No edit rights (403)**: The user does not have edit rights to the plan or scenario and cannot upload data.
