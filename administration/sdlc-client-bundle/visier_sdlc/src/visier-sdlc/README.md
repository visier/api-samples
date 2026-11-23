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
2. Configure each tenant's host, vanity, username, and password using `SOURCE_*` and `TARGET_*` values from `.env.example`. Visier authentication supports username/password only. Configure target-tenant IDs when operating through an administrating tenant.
3. Start without `INITIAL_SOURCE_VERSION_ID` and `INITIAL_TARGET_VERSION_ID` to choose a verified source and target pair using **Reset sync baseline** in the app. Promotion to an existing production tenant stays blocked until both baselines are set. Alternatively, set both environment values to seed a missing checkpoint once; they do not overwrite subsequent syncs. Never choose unrelated versions merely to enable sync. An empty production tenant can receive a first sync without a baseline.
4. Restart the server. Use **Connections** to see the active mode, tenant names, tenant vanity, API base URI, and API username for each environment. Both environments also show **Authentication method: Basic Authentication** as a fixed display value. Missing settings show **Not configured**; demo environments show **Not applicable (demo)**. Passwords and session tokens are never returned to the browser or saved in the state store.

`SOURCE_TENANT_ID` and `TARGET_TENANT_ID` override the tenant for API calls using the `TargetTenantID` header. Leave them blank when payload calls target the administrating tenant you logged into; the header is omitted. Set an override only when addressing a different managed tenant through that login, using its actual tenant ID, **not its vanity name**. A successful token request followed by `HTTP 401; code=VSE_AUTHENTICATION_INVALID_TOKEN` can indicate an incorrect override. Authentication errors identify the source/target, token request or API endpoint, HTTP status, and available Visier error code/correlation ID in the browser and server log. Raw response bodies, credential values, and headers are excluded.

The SDK obtains and renews session tokens internally using the configured username/password. An API request rejected with HTTP 401 is retried once with renewed authentication. GET/HEAD requests also retry once after a dropped connection, renewing authentication first. These recoveries share a limit of two API attempts per request. Writes are never replayed after a connection failure because they may already have taken effect. Persistent failures are reported normally.

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

Tenant credentials are Unity Catalog secrets in `catalog_name.schema_name`, named `{secret_prefix}{source|target}-{field}` (for example `visier-sdlc-source-host`). The deployment provisions four fields per tenant: `host`, `vanity`, `username`, and `password`. The app reads them at startup with its service principal through the SDK (`UnityCatalogSecretsCredentials`), because Apps resources cannot reference Unity Catalog secrets. It is configured by `VISIER_SECRETS_CATALOG`, `VISIER_SECRETS_SCHEMA` and `VISIER_SECRET_PREFIX`, all supplied by the bundle. The Spark example (`examples/databricks_bootstrap.py`) takes a `get_secret` callable you provide and is independent of this.

### Initialize and deploy

Choose one of the two routes below. The CLI route requires a local checkout, the Databricks CLI, and Python dependencies. The Apps UI route can be completed in the browser after an administrator provisions the table and tenant secrets. Run bundle commands from `visier_sdlc/`, where `databricks.yml` lives.

**Deployment values and defaults**

`deployment.template.json` lists the bundle variable names without the environment-only `BUNDLE_VAR_` prefix. Catalog, schema, warehouse ID, app name, and all eight tenant values are empty inputs. The only populated defaults are `secret_prefix`, `state_table_name`, and the `source_name` / `target_name` UI labels (Development / Production). The catalog and schema must already exist. Secret names and the qualified table name are derived internally from these values.

**Two supported deployment routes**

Use either local CLI deployment or direct deployment from Git in Databricks Apps. Uploading application files through the workspace UI and using the workspace bundle editor are outside the documented deployment paths.

| | Local CLI (bundle) | Apps: Deploy from Git |
| --- | --- | --- |
| Source location | The bundle is rooted at `visier_sdlc/` | Set Source code path to `visier_sdlc/src/visier-sdlc` |
| Configuration | `databricks.yml`, bundle variables, and app resource configuration | The app's `app.yaml` plus resource selections in the Apps UI |
| Deployment values | Choose a JSON settings file or `BUNDLE_VAR_*` environment variables | Select resources in Apps and provision secrets in Catalog Explorer; bundle variable files are not read |
| Table and warehouse | Defined as bundle app resources | Create/select existing resources, then attach them to the app |
| Tenant secrets | `setup_secrets` provisions and grants UC secrets | Provision in Catalog Explorer or run the same local `setup_secrets` bundle command |
| Start/update code | `databricks bundle run visier_sdlc_app` | Deploy the selected Git branch, tag, or commit in Apps |

**1. Local CLI deployment**

Clone the repository locally, authenticate with `databricks auth login --profile <profile>`, and set `DATABRICKS_CONFIG_PROFILE` to that profile. From `visier_sdlc/`, install the Python requirements in an active virtual environment; this is required for both configuration options:

```sh
cd src/visier-sdlc
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cd ../..
```

Then choose **one of two ways to provide deployment values**:

| Option | How to supply values | Variable names |
| --- | --- | --- |
| **A. JSON settings file** | Copy `deployment.template.json` to `.databricks/bundle/default/variable-overrides.json` and fill in the copy | `catalog_name`, `schema_name`, etc. |
| **B. Environment variables** | Set values in the environment from which you run deployment, directly or through `.env` | `BUNDLE_VAR_catalog_name`, `BUNDLE_VAR_schema_name`, etc. |

Both options configure the same bundle variables and use the same deployment script. You do not need to create a JSON settings file when using environment variables.

**Option A: JSON settings file**

Keep `deployment.template.json` as an empty, copyable template. Databricks bundle commands read `.databricks/bundle/default/variable-overrides.json` for this bundle's `default` target. To use a JSON values file, copy the template to that exact path, then edit the copy:

```sh
mkdir -p .databricks/bundle/default
cp deployment.template.json .databricks/bundle/default/variable-overrides.json
chmod 600 .databricks/bundle/default/variable-overrides.json
```

Only run the copy command for first-time setup: it overwrites an existing values file. Fill in the empty inputs in the copy and keep the committed template empty. The file contains passwords; `.databricks/` is git-ignored, and it must remain private. No generator or intermediate `deployment.json` is needed. A file named `deployment.json` is not automatically read by either route.

The JSON keys are bundle variable names without the environment-only `BUNDLE_VAR_` prefix. Environment variables and `--var` flags take precedence over the native file. Use the same target and configuration for deployment and subsequent run commands. The environment option below does not require this file.

**Option B: environment variables**

Set the `BUNDLE_VAR_*` values in the shell from which you will deploy. No JSON settings file is required. Use the syntax for your OS:

macOS or Linux (bash or zsh):

```sh
export BUNDLE_VAR_catalog_name=<catalog>
export BUNDLE_VAR_schema_name=<schema>
export BUNDLE_VAR_app_name=<app-name>
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

Alternatively, copy `.env.template` to `.env` and fill in its `BUNDLE_VAR_*` entries:

```sh
cp .env.template .env
```

Keep `.env` local; it is git-ignored and contains passwords. Use `dotenv run --` to load these values into the deployment command's environment.

**Deploy with the selected values**

From `visier_sdlc/`, with the Python environment still active, run:

```sh
./deploy.sh
# If using .env to supply BUNDLE_VAR_* values:
# dotenv run -- ./deploy.sh
```

The script validates the bundle, checks for deleted apps still tracked in deployment state, creates the state table, deploys the app resources, provisions secrets and grants access, then starts the app. Check the app's status and logs after starting it. The CLI synchronizes source files to Databricks as part of deployment; customers do not need to upload files manually.

If an app was deleted outside the bundle, Databricks CLI 1.25.0 can crash in `ResourceApp.OverrideChangeDesc` while planning its recreation. The script checks bound apps against the workspace and runs `bundle deployment unbind` only for an app confirmed missing. Deployment then recreates the app, and secret provisioning grants its new service principal access. Existing apps and other bundle resources keep their bindings; authentication, permission, or network failures stop deployment without unbinding the affected app. Use `./deploy.sh` for this recovery rather than running `databricks bundle deploy` directly.

`./deploy.sh` automatically runs `databricks bundle run prepare_deploy` before deployment. This is a repair for stale bundle bindings, not table or secret provisioning. When running the bundle deployment steps manually, call it before `databricks bundle deploy`, using the same profile, target, and variables. It does nothing when no bound app is missing. It is unnecessary for Apps UI/Git deployments, including local provisioning for a UI-created app.

**Undeploy the CLI bundle**

Use the same Python environment, workspace profile, and bundle variable values as deployment. From `visier_sdlc/`, preview the cleanup, then run it:

```sh
./undeploy.sh --dry-run
./undeploy.sh
# If using .env:
# dotenv run -- ./undeploy.sh --dry-run
# dotenv run -- ./undeploy.sh
```

Undeployment removes the bundle-managed app and its dedicated service principal, the SQL setup job, uploaded bundle files, the configured state table **with all promotion state and history**, and the eight `{secret_prefix}{source|target}-{host|vanity|username|password}` secrets. It revokes the app principal's table, secret, and schema setup grants before deleting the app. It does not attempt to revoke `USE_CATALOG`, which is inherited through the app principal's membership in `account users`. The catalog, schema, SQL warehouse, manually created optional `tenant-id` secrets, and local configuration files remain. The app's grants on optional `tenant-id` secrets are revoked too. This script does not undo changes already promoted to Visier tenants.

**This is a full cleanup of the configured table and eight secrets, including objects that existed before deployment.** Setup does not record whether those objects were created or reused, and it cannot restore overwritten secret values. Review the preview and use the original deployment values; do not run it against a table or secrets shared with another app. Cleanup requires permission to delete the table and secrets and to revoke the app principal's table, secret, and schema setup grants.

The script asks you to type `undeploy` before changing resources. Pass `--yes` to confirm for unattended runs. Missing resources are skipped so a partial cleanup can be retried; other errors stop the script. If a crashed deployment left a lock, use `./undeploy.sh --force-lock` only after confirming no deployment is running. The script is for the CLI bundle route; it does not delete an untracked app created through the Apps UI.

**2. Direct deployment from Git**

This route fetches the app source directly from GitHub (or another supported Git provider). It does not read the JSON template or a populated deployment values file, and it does not run `databricks.yml`, `deploy.sh`, or the setup scripts. An administrator must provision the table and secrets before the first successful app start. No local checkout is required when following these browser-based steps:

1. In the SQL editor, create the state table in your chosen catalog and schema using the structure in `deploy-assets/databricks/state-table.sql` (view the file in GitHub and replace the example catalog/schema/table names). The catalog and schema must already exist. Select a SQL warehouse that can query the table.
2. In **Databricks Apps**, create a custom app and configure its Git repository. For a private repository, configure the app service principal's Git credential. Note the app's service principal identity from the app details; it will receive access to the secrets.
3. In the app's resource settings, attach the SQL warehouse under the exact resource key **`sql-warehouse`**, with **Can use**, and the state table under **`promotion-state`**, with **Can select and modify**. The table's full name is supplied to the runtime, which derives the catalog and schema used for tenant secrets. Do not enter them again in `app.yaml`.
4. In **Catalog Explorer**, open that same catalog and schema. Use **Create → Secret** to create the eight Databricks-managed secrets below, entering each tenant's actual value:

   | Source secret | Target secret | Value |
   | --- | --- | --- |
   | `visier-sdlc-source-host` | `visier-sdlc-target-host` | Tenant API host URL |
   | `visier-sdlc-source-vanity` | `visier-sdlc-target-vanity` | Tenant vanity |
   | `visier-sdlc-source-username` | `visier-sdlc-target-username` | API username |
   | `visier-sdlc-source-password` | `visier-sdlc-target-password` | API password |

   These names use the committed `app.yaml` prefix, `visier-sdlc-`. Open each secret's **Permissions → Grant** and grant the app's service principal **READ SECRET**. Ensure it also has **USE CATALOG** and **USE SCHEMA** on the parents, and **SELECT** and **MODIFY** on the attached state table. Adding the table resource normally establishes the table and parent privileges. Creating secrets requires **CREATE SECRET** on the schema (or ownership); granting access requires ownership or **MANAGE**. Do not put the secret values in GitHub or `app.yaml`.
5. In Apps, choose **Deploy → From Git**, select the branch, tag, or commit, set **Source code path** to `visier_sdlc/src/visier-sdlc`, and deploy. Check the app's status and logs. For later code changes, redeploy from Git. After changing secrets, restart or redeploy the app so it reloads the values.

**Optional local provisioning for a UI-created app:** Use the CLI to provision both the table and secrets instead of the browser steps 1 and 4. Clone the repository locally, install the Python requirements using the CLI setup instructions above, and authenticate to the intended workspace. For a local named profile, set `DATABRICKS_CONFIG_PROFILE=<profile>` after `databricks auth login --profile <profile>`. The catalog and schema must already exist, and the app must already have been created in Apps so its service principal exists. From the checkout's `visier_sdlc/` directory, choose the same configuration options as CLI deployment: either fill `.databricks/bundle/default/variable-overrides.json` from `deployment.template.json`, or supply `BUNDLE_VAR_*` environment variables. Set `app_name` to the existing UI-created app's name and use the same warehouse, table, catalog, schema, and secret prefix that the app will use. With a JSON settings file or exported variables, run:

```sh
databricks bundle run setup_table
databricks bundle run setup_secrets
```

If supplying `BUNDLE_VAR_*` through a local `.env` copied from `.env.template`, load it for both commands:

```sh
dotenv run -- databricks bundle run setup_table
dotenv run -- databricks bundle run setup_secrets
```

These commands create the table if missing, create/update the supported tenant secrets, and grant the app access to the secrets and state table. They run local scripts using bundle-resolved settings and authentication; they do not deploy bundle resources, take ownership of the UI-created app, or start it. Complete the resource attachments in step 3 and deploy from Git in step 5. No `prepare_deploy`, `bundle deploy`, or `./deploy.sh` is needed for this route. Your provisioning identity needs permission to create the table and secrets and grant the app access.

Use `databricks bundle run` for setup with either configuration option. The CLI resolves native JSON settings, `BUNDLE_VAR_*` environment variables, and `--var` overrides using its standard precedence, then passes resolved values to both scripts under the same `BUNDLE_VAR_*` names. Legacy script names such as `CATALOG`, `SCHEMA`, `TABLE`, and `SECRET_SOURCE_PASSWORD` are no longer read. Calling a Python script directly bypasses bundle settings-file resolution. A JSON settings file must be at the native path above; `deployment.template.json` is only a template.

The committed `app.yaml` contains only resource keys and application defaults: `visier-sdlc-`, Development, and Production. Direct Git deployment uses those defaults. For custom labels or a different prefix in this route, change those three application defaults in `app.yaml` on a customer-controlled branch/fork, and use the same prefix during secret provisioning. The bundle route instead supplies them as variables without changing source. Do not put credential values, catalog/schema names, warehouse IDs, or app names in `app.yaml`. This is the main configuration difference between the routes; a local JSON file cannot alter code fetched directly from Git by the Apps UI.

Choose one route to manage each app. Switching an existing app between bundle ownership and UI-managed resources requires reconciling its configuration; a later bundle deployment can reapply bundle settings.

References: [Databricks variable files and precedence](https://docs.databricks.com/aws/en/dev-tools/bundles/variables), [Unity Catalog secret creation and permissions](https://docs.databricks.com/aws/en/security/secrets/unity-catalog-secrets), [web terminal authentication](https://docs.databricks.com/aws/en/compute/web-terminal), [Apps deployment from Git](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy), and [app resource environment values](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/environment-variables).

The bundle provisions the four tenant fields per role listed in the JSON template. The app also supports an optional `{secret_prefix}{source|target}-tenant-id` secret for managed-tenant access; create it separately if needed. `setup_secrets` grants access only to these supported tenant fields. Old API-key, OAuth, or directly supplied token secrets are not read or newly granted access. Existing grants are not revoked; remove obsolete credentials and grants separately. The deployment sequence is:

1. `databricks bundle run setup_table` creates the state table before app resource registration, using the SQL warehouse as the deploying user. The catalog and schema must already exist; the deploying user needs permission to create the table.
2. `databricks bundle deploy` creates the app and its service principal; the app's `promotion-state` resource grants it `MODIFY` on the existing state table.
3. `databricks bundle run setup_secrets` creates or updates the secrets from the `secret_*` variables, then grants the app's service principal `READ_SECRET` on the supported prefixed tenant secrets, plus `USE CATALOG` and `USE SCHEMA`. A failed `USE CATALOG` grant only prints a warning (many workspaces grant it implicitly to all account users); a failed `USE SCHEMA` or `READ_SECRET` grant is an error. It is a local script (`scripts:` in `resources/secrets.yml`, running `scripts/setup_secrets.py`) because bundles have no native Unity Catalog secret resource, and running it locally means secret values never enter the bundle or a deployed job. An empty variable leaves the existing secret untouched, so you can rerun it to rotate one value or to re-grant after adding secrets. It fails if the `source-host` or `target-host` secret does not exist afterwards. It also grants `SELECT` and `MODIFY` on the state table. You need `CREATE_SECRET` on the schema (and `MANAGE` on existing secrets), plus permission to grant access to the table.
4. `databricks bundle run visier_sdlc_app` starts (or restarts) the app. It initializes its state row and fails at startup if the table or a required secret is missing.

Secret variables default to empty rather than being prompted for: the CLI resolves every variable for every command, so required variables would prompt for passwords on each `deploy`. Values passed with `--var`, or typed at a prompt, may be recorded in shell history or logs, which is another reason to prefer `BUNDLE_VAR_*` from a secrets manager. After changing secrets, restart the app.

The setup script grants both `SELECT` and `MODIFY` on the state table because the app needs reads as well as writes. The grants call uses the REST permissions API with the `secret` securable type, which the SDK enums lack; it has not been run against a workspace.

Provision a Delta table before launching replicas (the bundle's `setup_table` script does this; `sql_setup_job` remains available to rerun the same idempotent SQL as a job):

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
