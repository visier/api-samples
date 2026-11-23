# Visier tenant promotion

A Flask-backed single-page app for promoting production versions from a Visier development tenant to production. The default is a persistent, isolated **demo workspace**; live mode uses `visier-platform-sdk` for every tenant operation.

## Run locally

Use Python 3.11 or later with OpenSSL. Python 3.9 is supported by the code and SDK, but Apple's bundled Python uses LibreSSL, which the SDK's urllib3 dependency warns is unsupported for live HTTPS connections.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
python app.py
```

Open **http://127.0.0.1:5050**. No JavaScript build or Node installation is required. Your existing pip/Artifactory configuration is used; no repository URL or credentials belong in requirements files. The implementation was verified with SDK `22222222.99201.3254`, fetched from the configured Artifactory.

The demo starts with three pending development versions, a disabled last-synced baseline, and one production drift version. Roll back, select a development version, then sync. Selecting v127 includes v126; v128 remains pending. Use **Simulate production drift** to exercise rollback again. Demo history and sync state survive app restarts in `instance/promotion.sqlite3`; demo and live state use separate tenant-pair keys.

## Visual styling

The app follows [Visier’s website](https://www.visier.com/) with a mid-tone cream page (`#f6f0e8`), pale cards and tab surfaces (`#fbf8f4`), deeper cream table headers (`#f1e7db`), dark neutral text, and coral accents (`#f1481d`). The official rounded SVG wordmark is all black, with Visier’s official 512 × 512 coral tile and light V displayed beside it. The same high-resolution tile is used for the favicon and compact navigation. Instrument Sans and Crimson Pro are bundled locally; their licenses are in `static/FONT-LICENSES.txt`. The home-screen icon is the official Visier coral icon. Fonts and artwork require no external requests at runtime.

## Live tenant setup

1. Set `APP_MODE=live` in `.env`.
2. Configure `SOURCE_*` and `TARGET_*` values from `.env.example`. Provide each tenant's host, vanity, and username/password, or an access/ASID token. `SOURCE_APIKEY` and `TARGET_APIKEY` are optional; leave them blank or unset when your server does not require an API key. The SDK also accepts client ID and client secret with username/password for two-legged OAuth. Set `TARGET_CLIENT_ID` and `TARGET_CLIENT_SECRET` for the target if applicable. Configure target-tenant IDs when operating through an administrating tenant.
3. Start without `INITIAL_SOURCE_VERSION_ID` and `INITIAL_TARGET_VERSION_ID` to choose a verified source and target pair using **Reset sync baseline** in the app. Promotion to an existing production tenant stays blocked until both baselines are set. Alternatively, set both environment values to seed a missing checkpoint once; they do not overwrite subsequent syncs. Never choose unrelated versions merely to enable sync. An empty production tenant can receive a first sync without a baseline.
4. Restart the server. Use **Connections** to see the active mode, tenant names, tenant vanity, API base URI, and API username for each environment. Both environments also show **Authentication method: Basic Authentication** as a fixed display value. Missing settings show **Not configured**; demo environments show **Not applicable (demo)**. Passwords, API keys, client secrets, and tokens are never returned to the browser or saved in the state store.

`SOURCE_TENANT_ID` and `TARGET_TENANT_ID` override the tenant for API calls using the `TargetTenantID` header. Leave them blank when payload calls target the administrating tenant you logged into; the header is omitted. Set an override only when addressing a different managed tenant through that login, using its actual tenant ID, **not its vanity name**. A successful token request followed by `HTTP 401; code=VSE_AUTHENTICATION_INVALID_TOKEN` can indicate an incorrect override. Authentication errors identify the source/target, token request or API endpoint, HTTP status, and available Visier error code/correlation ID in the browser and server log. Raw response bodies, credential values, and headers are excluded.

With username/password configured, expired sessions renew silently through the SDK. An API request rejected with HTTP 401 is retried once with renewed authentication; an OAuth refresh token rejected with `invalid_grant` falls back to a fresh login. GET/HEAD requests also retry once after a dropped connection, renewing authentication when credentials are available. These recoveries share a limit of two API attempts per request. Writes are never replayed after a connection failure because they may already have taken effect. Persistent failures are reported normally. Supplied access/ASID tokens without username/password cannot log in again automatically; replace them when they expire.

Live mode has no demo mutation controls. SDK methods and real SDK DTO serialization are covered by tests. Read-only live authentication and version-history checks have passed for both configured tenants; validation has not modified either tenant. The version tables show each version’s description, ID, and `versionNumber` (normalized as `number` in the app API). When Visier omits `versionNumber`, its column displays “—”. Owner and publish-date columns are omitted because the production-version API does not provide those fields.

## Workflow and safeguards

- Before confirming a sync, edit **Draft project display name** (up to 50 characters) to distinguish the production draft. It defaults to **Development tenant promotion** for each sync. Use the separate **Description** field for longer notes. **Version number** is calculated automatically from the latest production version plus one; an empty production history or missing version number starts at 1. These details are saved with the operation in the activity history.
- Version order comes from Visier's newest-first production history, including pagination. Selecting an endpoint includes every older unsynced development version. The synchronized source baseline remains disabled and earlier source history is hidden.
- Sync exports the inclusive oldest-to-selected range as ZIP, creates a target draft, uploads the raw ZIP, then runs `commitAndPublish`. Only a response containing the confirmed published version ID advances the checkpoint.
- A target head different from the persisted production checkpoint is drift. Sync stays blocked until rollback succeeds or an operator verifies an external fix and resets the baseline. Historical drift remains in the production history after its changes are reversed.
- During publication, newly visible production versions show **Awaiting confirmation** until the checkpoint is saved, rather than triggering a temporary drift warning. An uncertain publication keeps those versions unconfirmed and requires reconciliation. Existing drift remains visible, and refreshes retry if the saved operation or checkpoint changes while histories are being read.
- `rollBackTo` creates a draft containing inverse changes, per the supplied API. The app **also commits and publishes that draft**, then saves the new production head while retaining the source baseline.
- Both histories refresh after operations, on demand, and every 30 seconds while the page is visible. Open review dialogs retain the original state fingerprint, so a stale confirmation is rejected.
- A durable operation claim and atomic compare-and-swap prevent concurrent app workers from publishing the same selection. Target history is checked again immediately before publication. Visier exposes no conditional publish/precondition parameter, so a direct production writer can still race the final API call; restrict concurrent tenant publication operationally.
- Export/import failures preserve the checkpoint and record the failed attempt. Drafts are retained for inspection. A publication rejected with HTTP 401/403 is marked **Publication denied**; fix the target user's permissions and use **Recover operation** to retry the same draft. Timeouts, missing confirmation, and crashes require verification in Visier before recovery. Draft deletion is an explicit recovery choice.

## Unversioned source migration

Open **Unversioned sources**, select **Replace all existing target sources**, and choose **Migrate sources** to copy all current source definitions from the development tenant to production. The button stays disabled until the checkbox is selected. The app sends `POST /v1beta/admin/sources` with `{"operation":"exportSources"}`, validates the returned ZIP, and sends its unchanged bytes to `PUT /v1beta/admin/sources` on the target tenant as `application/zip`. Each call uses that tenant's credentials and optional `TargetTenantID` override.

The interface sets `replaceAllExistingSources=true`; this removes all existing target sources before importing the development sources. The review dialog shows this behavior before confirmation. The API also supports `false`: matching sources are updated and target-only sources are kept. Export includes the current sources at execution time; the review does not capture a source snapshot or detect source changes made outside this app.

Source imports apply directly, independently of production version drift or the version baseline. They do not create a draft, publish a production version, or advance the version checkpoint. Version rollback cannot undo a source import. The result and activity log show Visier's `created`, `updated`, `ignored` (unchanged), and `deleted` counts. Demo mode simulates both import modes and persists the resulting source definitions.

The app endpoint is `POST /api/sources/migrate`, with a JSON body containing the current `/api/state` `fingerprint` and optional boolean `replace_all_existing_sources` (default `false`). It returns `message` and `summary`. Source migrations share the durable operation lock with version syncs, rollbacks, and baseline resets. A completed source attempt invalidates older confirmations. Source export failures release the lock without changing target sources; an import error, missing summary, or interrupted operation requires inspection and reconciliation before another operation can start.

## Recover an interrupted operation

For a failed or interrupted **production promotion or rollback**, choose **Recover operation** in the status banner. This also works for existing operations locked by earlier app versions. Inspect the operation/draft in Visier and ensure the original request or worker is no longer running, then choose:

- **Retry publishing this draft** after fixing permissions or another publish problem and verifying it was never published. The app reuses the prepared draft without creating or importing another project. Production must still have the same latest version as when the draft was prepared.
- **Delete draft and start again** after verifying it was never published. Deletion releases the operation without advancing the checkpoint. If deletion fails, retry it or dismiss the operation; a missing draft is treated as already deleted.
- **Publication completed — confirm version** if Visier shows a successful publication whose response was lost. Select the new version belonging to this operation; this updates the checkpoint without publishing again.
- **Dismiss operation and keep any draft** after verifying it was never published. This releases the operation without advancing the checkpoint or deleting the draft, so users without delete permission can still continue. Clean up any retained draft in Visier. Use this for interrupted preparation too; partially imported drafts cannot be retried directly. If creation was interrupted before its ID was saved, inspect Visier for an unfinished draft.

Recovery requires explicit outcome verification and rejects stale reviews and simultaneous recovery attempts. When Visier returned a confirmed publication ID but saving the checkpoint failed, only confirmation of that version is allowed. New production versions block retrying the old draft; review whether the publication completed or another writer changed production. Dismissal/deletion leaves external production changes subject to the normal drift checks. Permission or connection configuration changes may require restarting the app; the saved draft and recovery choices survive restarts.

Command-line recovery remains available. Inspect the operation/draft ID and verify its outcome in Visier. Ensure the original worker is stopped, then run these commands with the same environment and state store as the app:

```sh
# ONLY after confirming which production version this operation published:
python -m flask --app app:create_app reconcile --target-version-id CONFIRMED_VERSION_ID

# OR ONLY after confirming the operation was never published:
python -m flask --app app:create_app reconcile --not-published
```

For an interrupted **source migration**, inspect the target sources and ensure the original worker is stopped. Then choose exactly one source outcome:

```sh
# ONLY after verifying that the source import completed:
python -m flask --app app:create_app reconcile --sources-imported

# OR after inspecting any partial changes and confirming the import did not complete:
python -m flask --app app:create_app reconcile --not-imported
```

Source reconciliation records the operator's finding without changing the version checkpoint. A manually confirmed success has no fabricated import counts. Version recovery flags cannot resolve a source migration, and source recovery flags cannot resolve a version operation.

For version recovery, `--target-version-id` verifies the production version exists, advances the checkpoint, and records success. `--not-published` clears the claim without advancing the checkpoint or deleting the draft. Recovery is an operator assertion, not an automatic inference. For a Databricks bootstrap, point Flask at that bootstrap's app factory so recovery uses the same table and secrets. Refresh the UI afterward.

The in-app endpoint is `POST /api/operations/recover` with `operation_id`, integer `state_revision` from `/api/state`, `action` (`retry`, `discard`, `published`, or `dismiss`), and `verified: true`. The `published` action also requires `target_id`. Source imports continue to use the source-specific CLI outcomes above.

## Reset the sync baseline after an external fix

Use **Reset sync baseline** in the baseline or drift warning, or open the dropdown beside **Sync to production** and choose its second option, **Reset sync baseline**. The dropdown remains available when drift or an empty promotion selection disables sync. The drift-warning action opens a target-only reset with the current production head selected. Use this when promotion problems were resolved outside the app, or when you need to repair a missing or incorrect checkpoint. Choose **Source only**, **Target only**, or **Source and target**, then select the verified version IDs. The dialog includes the full histories, including source versions hidden from the normal promotion list. It previews both the saved and proposed version pairs before confirmation. A one-sided reset preserves the other version ID; a missing checkpoint requires explicitly choosing both IDs, with **Source and target** fixed as the scope.

Provide a reason and confirm that source changes through the chosen baseline are already accounted for in the target, and that accepted production changes will not cause merge conflicts with pending development changes. **Confirm baseline reset** stays disabled until both resulting versions exist, at least one differs from the saved pair, a nonblank reason is provided, and the verification checkbox is checked. This allows compatible production-only differences. The app checks that both IDs exist, but cannot establish content equivalence or detect merge conflicts for you. Source changes through the chosen baseline will be excluded from future syncs; choosing an older source version makes its newer versions pending again. The target baseline becomes the rollback point. Choosing the current target head accepts externally resolved changes or production changes verified not to conflict with pending development changes; choosing an older target version leaves newer production versions flagged as drift and keeps sync blocked.

Resetting the baseline only changes the saved checkpoint: it does not export, import, roll back, or publish tenant changes. The activity log retains previous records and adds the reason, timestamp, scope, and old/new checkpoint pairs. The summary shows **Baseline reset** rather than claiming a successful sync. Resets survive restarts and are protected against stale confirmations and concurrent state updates. Active or uncertain operations must be reconciled first using the recovery procedure above.

If accepted production changes turn out to conflict, choose **Restore previous baseline** from the sync dropdown to prefill the prior version pair, review it, and confirm. Restoring the older target baseline flags the accepted versions as drift again, blocks sync, and enables **Roll back**. This shortcut remains available after a failed preparation attempt as long as the checkpoint still matches the most recent reset and the previous versions exist. You can also select an earlier pair manually using **Reset sync baseline**. Restoring a baseline is recorded as another reset, preserving both decisions in the activity log; it does not itself roll back production.

`INITIAL_SOURCE_VERSION_ID` and `INITIAL_TARGET_VERSION_ID` remain first-run seeds only. Changing them does not overwrite an existing checkpoint; no force-on-startup setting is needed.

### Switching Visier deployments or starting with empty state

State is scoped to the source/target identity (`host`, `tenant_id`, and `vanity`), not to the login password. After changing deployment secrets, restart or redeploy the app so it reads the new configuration. A new tenant pair gets its own state; keep the old pair's row to retain its history and any unresolved operation. For the same pair, use **Reset sync baseline** to correct the checkpoint while preserving that history.

The Databricks Apps entry point (`wsgi.py`) automatically initializes a missing pair row with revision `0` and document `{}` in the existing table. An empty table therefore no longer prevents startup. With an existing target, the app shows **Review the sync baseline**, blocks version sync and rollback, and offers **Reset sync baseline** to choose both verified versions. Leave both `INITIAL_*_VERSION_ID` values unset when you want to make this choice in the app; otherwise those values seed the empty checkpoint at startup. An empty target can still receive its first sync without a baseline.

Avoid truncating `promotion_state` as a routine reset: it removes every pair's checkpoints, activity, and recovery claims. If it has already been truncated, restart the updated app, inspect any interrupted tenant operations, and set verified baselines. Restarting the app recreates a missing state row without overwriting an existing one; then set both baselines in the UI.

## Architecture

| Component | Responsibility |
| --- | --- |
| `static/` | Responsive browser SPA, cumulative version selection, review dialogs, activity and connection views |
| `app.py` | Flask factory, validation, same-origin write checks, safe errors, recovery CLI |
| `promotion/service.py` | Sync, drift, rollback and checkpoint logic, independent of Flask and SDK DTOs |
| `promotion/ports.py` | Tenant gateway, credential-provider, and atomic state-store contracts |
| `promotion/visier.py` | Typed SDK calls, binary ZIP export/import, pagination and response normalization |
| `promotion/demo.py` | Persistent simulated source and target tenants behind the same gateway contract |
| `promotion/storage.py` | SQLite and injectable Databricks Delta table state adapters |
| `promotion/credentials.py` | Environment/dotenv and injectable Databricks secrets providers |

Inject `store`, `credentials`, and/or `gateway` into `create_app()` to replace infrastructure. The store persists a document with its checkpoint, operation claim, and activity history in one atomic update. Deploy all workers for one tenant pair against the same durable store.

## Databricks storage and secrets

`examples/databricks_bootstrap.py` provides `build_app(spark, get_secret)`. It expects an already configured Spark/Delta runtime and a callable such as `dbutils.secrets.get`; it does not assume a particular Databricks hosting product provides these objects in its web workers. In a Databricks App without Spark, provide a configured Databricks Connect session or implement the small `StateStore` contract using the available table API. The SQLite adapter is intended for local testing.

The bundle supplies `VISIER_SECRETS_CATALOG` from `catalog_name`, `VISIER_SECRETS_SCHEMA` from `schema_name`, and `PROMOTION_STATE_TABLE` from `state_table_name`. Set the table to an unqualified name such as `promotion_state`; the app composes `catalog.schema.promotion_state` using those catalog and schema values. The manual provisioning script uses the same settings. Each component must be a simple identifier (letters, digits, or underscores, starting with a letter or underscore).

Tenant credentials are Unity Catalog secrets in `catalog_name.schema_name`, named `{secret_prefix}{source|target}-{field}` (for example `visier-sdlc-source-host`). `host` is required for each role; the other fields depend on the auth method: `vanity`, `username`, `password` (basic), `access-token` or `asid-token` (token), and optionally `api-key`, `tenant-id`, `client-id`, `client-secret`. The app reads them at startup with its service principal through the SDK (`UnityCatalogSecretsCredentials`), because Apps resources cannot reference Unity Catalog secrets. It is configured by `VISIER_SECRETS_CATALOG`, `VISIER_SECRETS_SCHEMA` and `VISIER_SECRET_PREFIX`, all supplied by the bundle. The Spark example (`examples/databricks_bootstrap.py`) takes a `get_secret` callable you provide and is independent of this.

### Initialize and deploy

One-time setup: authenticate with `databricks auth login`, then supply the bundle variables (`BUNDLE_VAR_*`) using one of the two options below. The secrets step runs locally and uses the Databricks SDK, so its requirements must be installed. Run all bundle commands from `visier_sdlc/`, where `databricks.yml` lives.

**Option 1: `.env` file with `dotenv run`**

1. Copy the template and provide the actual values:

   ```sh
   cp .env.template .env
   ```

   Edit `.env` and replace each empty value. `.env` is git-ignored, but it contains passwords, so keep it local.

2. Set up a virtual environment, install the requirements, and activate it:

   ```sh
   cd src/visier-sdlc
   python3 -m venv .venv
   source .venv/bin/activate            # Windows: .venv\Scripts\activate
   python -m pip install -r requirements.txt
   cd ../..
   ```

3. Prefix each Databricks CLI bundle command with `dotenv run --`, for example:

   ```sh
   dotenv run -- databricks bundle deploy
   dotenv run -- databricks bundle run sql_setup_job
   ```

**Option 2: export the variables into the shell**

Export the same variables in your shell, then run the Databricks CLI commands directly, without `dotenv`. Use the syntax for your OS.

macOS or Linux (bash or zsh):

```sh
export BUNDLE_VAR_warehouse_id=<id>
export BUNDLE_VAR_secret_source_host=https://...
export BUNDLE_VAR_secret_source_vanity=...
export BUNDLE_VAR_secret_source_username=...
export BUNDLE_VAR_secret_source_password=...
export BUNDLE_VAR_secret_target_host=https://...
export BUNDLE_VAR_secret_target_vanity=...
export BUNDLE_VAR_secret_target_username=...
export BUNDLE_VAR_secret_target_password=...
```

Windows (PowerShell):

```powershell
$env:BUNDLE_VAR_warehouse_id = "<id>"
$env:BUNDLE_VAR_secret_source_host = "https://..."
# ...set the remaining BUNDLE_VAR_* values the same way
```

Remember that the Python environment for the secrets step still needs `pip install -r src/visier-sdlc/requirements.txt` in an active virtual environment, as in Option 1.

The bundle manages only these four fields per role. The app also reads other fields (`api-key`, `tenant-id`, `client-id`, `client-secret`, `access-token`, `asid-token`) when a secret with that name exists; if you need one, create it yourself with `databricks secrets-uc create-secret`, and `setup_secrets` will grant access to it too. Then:

1. `databricks bundle deploy` creates the app and its service principal; the app's `promotion-state` resource grants it `MODIFY` on the state table.
2. `databricks bundle run sql_setup_job` creates the state table.
3. `databricks bundle run setup_secrets` creates or updates the secrets from the `secret_*` variables, then grants the app's service principal `READ_SECRET` on every `{secret_prefix}*` secret, plus `USE CATALOG` and `USE SCHEMA`. A failed `USE CATALOG` grant only prints a warning (many workspaces grant it implicitly to all account users); a failed `USE SCHEMA` or `READ_SECRET` grant is an error. It is a local script (`scripts:` in `resources/secrets.yml`, running `scripts/setup_secrets.py`) because bundles have no native Unity Catalog secret resource, and running it locally means secret values never enter the bundle or a deployed job. An empty variable leaves the existing secret untouched, so you can rerun it to rotate one value or to re-grant after adding secrets. It fails if the `source-host` or `target-host` secret does not exist afterwards. You need `CREATE_SECRET` on the schema (and `MANAGE` on existing secrets).
4. `databricks bundle run visier_sdlc_app` starts (or restarts) the app. It initializes its state row and fails at startup if the table or a required secret is missing.

Secret variables default to empty rather than being prompted for: the CLI resolves every variable for every command, so required variables would prompt for passwords on each `deploy`. Values passed with `--var`, or typed at a prompt, may be recorded in shell history or logs, which is another reason to prefer `BUNDLE_VAR_*` from a secrets manager. After changing secrets, restart the app.

The service principal also needs `SELECT` on the state table for reads; the `MODIFY` resource grant may not imply it, so grant it yourself if the app reports a permission error. The grants call uses the REST permissions API with the `secret` securable type, which the SDK enums lack; it has not been run against a workspace.

Provision a Delta table before launching replicas (the bundle's `sql_setup_job` does this):

```sql
CREATE TABLE catalog.schema.promotion_state (
  pair STRING NOT NULL,
  revision BIGINT NOT NULL,
  document STRING NOT NULL
) USING DELTA;
```

For Databricks Apps, `wsgi.py` uses `SqlWarehouseStateStore.provision()` to initialize a missing tenant-pair row with a conditional `MERGE`. Grant the app permission to select, insert, and update the existing table and use its SQL warehouse. Existing rows are preserved, including active operation claims. If another startup wins the Delta transaction, startup proceeds only after reading a valid durable row. The app rejects duplicate rows; Delta does not enforce uniqueness on `pair`, so external writers must also avoid blind inserts. See [Databricks merge](https://docs.databricks.com/aws/en/delta/merge) and [write conflicts](https://docs.databricks.com/aws/en/optimizations/isolation/row-level-concurrency).

For the injectable Spark adapter in `examples/databricks_bootstrap.py`, provision **exactly one row per tenant pair** before startup: compute `pair = tenant_pair_key(credentials)` using the same secrets provider, then insert that pair with revision `0` and document `'{}'` once under administrator control. Both adapters check row cardinality, use a revision predicate for updates, and verify a unique write token. Delta concurrent-write conflicts fail the operation safely; no tenant write starts without a successful claim.

The Delta adapter and secrets injection are supplied, but have not been exercised against a Databricks workspace. Wire platform administrator authentication/authorization at your deployment ingress before exposing live tenant operations. The local server binds only to loopback; it deliberately has no hardcoded application users or passwords. Run the Flask app through your deployment's WSGI server, with its timeout high enough for tenant operations; if a request is interrupted, reconcile its durable claim before retrying. Same-origin write validation uses the app's public origin, taken from `DATABRICKS_APP_URL` (injected by Databricks Apps) or, when set, the `PUBLIC_ORIGIN` override (for example `https://your-app.example.com`) for other TLS-terminating proxies. If neither is set, the request's own host is used.

## Checks

```sh
python -m pytest -q
# Or, with the environment activated:
pytest -q
```

Tests cover cumulative ranges, checkpoint persistence, full and partial sync, drift and rollback, preparation errors, uncertain publish/reconciliation, multiple workers, stale state, missing baselines, request validation, and the installed SDK's DTO/method contracts. Browser checks cover review dialogs, rollback, cumulative selection and sync, both tabs, activity, connections, and responsive layouts.

Unversioned source promotion is intentionally a clearly marked future tab, as requested. No source APIs are invoked by this iteration.
