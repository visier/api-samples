# Planning Collaboration Administration

This is a sample script that manages plan collaborations using a two-phase approach:
1. **Leaf-to-Root Processing**: Consolidates and submits all subplan data to the root plan
2. **Root-to-Leaf Processing**: Reopens collaborations for the next planning cycle

The script uses the [Plan Administration API](https://docs.visier.com/developer/apis/references/api-reference.htm#tag/PlanAdministration) to manage plan hierarchies and collaborations.

## Getting Started

### Environment
Python 3.x installed on your system with the following dependencies:
- `pandas==2.3.2`
- `python-dotenv==1.1.1`
- `visier-platform-sdk==22222222.99201.2176.post3`

You can install them using pip and the provided `requirements.txt`:
```bash
pip install -r requirements.txt
```

## Configuration
Configure the `.env` file with the following environment variables:

### Authentication
This script authenticates using the [Visier Python SDKs](https://github.com/visier/python-sdk). For more authentication options, see [API Authentication](https://docs.visier.com/visier-people/Default.htm#cshid=1054).
```env
VISIER_HOST=https://customer-specific.api.visier.io
VISIER_API=visier-provided-api-key
VISIER_USERNAME=visier-username
VISIER_PASSWORD=visier-password
VISIER_VANITY=visier-tenant-vanity-name
```

### Script Configuration
```env
TARGET_PLAN_NAME=Your Root Plan Name
VERBOSE=false
```

- **`TARGET_PLAN_NAME`** (required): The name of the root plan you want to process. The script will look up the collaborating scenario for you. The user must have edit access to the plan. If the user is not the owner of the plan, see [How to Share Your Plan](https://docs.visier.com/visier-people/Planning/plan%20sharing/plan%20sharing.htm).
- **`VERBOSE`** (optional): Set to `true` to enable detailed logging output. Defaults to `false`.

## Usage

Run the script with:
```bash
python main.py
```

### What the Script Does

The script performs a two-phase workflow:

**Phase 1: Leaf-to-Root Processing (Deepest to Shallowest)**
- Processes all plans from leaf plans (deepest) to root plans (shallowest)
- For plans with open collaborations: consolidates → closes collaboration → submits
- For plans without open collaborations: submits directly
- Skips submission for root plans (they serve as containers)

**Phase 2: Root-to-Leaf Processing (Shallowest to Deepest)**
- Processes all plans from root plans (shallowest) to leaf plans (deepest)
- Starts collaborations for non-leaf plans
- Reopens all child plans

### Error Handling
The script will terminate if it encounters any fatal errors. In such cases, please review the log output for error details and resolution steps, then run the script again.

### Logging
- Set `VERBOSE=true` in your `.env` file to enable detailed logging
- Error messages are always displayed regardless of verbose setting 
