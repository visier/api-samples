# Visier SDLC Promotion Sample

Sample Python workflow for promoting Visier configuration from a **source** tenant to a **target** tenant using Visier's public Administration APIs and the official `visier-platform-sdk`.

The guarded default is a preview: authenticate the source tenant, read published history, choose the export range, and show the target draft metadata that would be used. No ZIP export, target draft creation, import, or publish happens unless you explicitly request it.

## Requirements

- Python 3.9+
- Access to source and target tenants with the required Administration API capabilities

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dependencies: `visier-platform-sdk`, `PyYAML`, and `python-dotenv`.

## Configure

1. Copy `config.yaml.example` to `config.yaml`.
2. Set `profiles.source` and `profiles.target` with each tenant's `base_url`, `api_key`, `username`, and `password`.
3. Prefer `${ENV_VAR}` placeholders in YAML and keep secrets in the environment or a `.env` file next to `config.yaml`.

The loader only reads `.env` from the config file's directory to avoid mixing credentials from another working directory. It rejects non-HTTPS base URLs and rejects configs where `source` and `target` clearly point to the same tenant.

## Promotion Modes

| Command | Effect |
| --- | --- |
| `python promote.py` | Preview only. Authenticates source, lists source history, chooses export ids, and prints planned target draft metadata. |
| `python promote.py --apply` | Applies target changes. Exports the ZIP, creates a target draft, and imports commits. Does not publish. |
| `python promote.py --apply --publish` | Applies target changes and runs `commitAndPublish`. This changes the target tenant's published configuration. |

`--publish` requires `--apply`. The old `--dry-run` flag is deprecated and now behaves like the default preview mode.

## Export Scope

| Flag | Meaning |
| --- | --- |
| `--mode latest` | Export only the most recent published version from the source. This is the default. |
| `--mode all` | Export full published history in one ZIP using a paginated source listing and an oldest-to-newest range. |
| `--config PATH` | Config YAML path. Defaults to `config.yaml` in the current working directory. |

## Workflow Steps

| Step | Tenant | What happens |
| --- | --- | --- |
| 0 | Source, and target only with `--apply` | Obtain a secure token through `visier-platform-sdk`. |
| 1 | Source | List published production versions with `GET /v1/admin/production-versions`. |
| 2 | Source | With `--apply`, export selected production versions as a ZIP. |
| 3 | Target | With `--apply`, create a new draft project. |
| 4 | Target | With `--apply`, upload the ZIP into the draft. |
| 5 | Target | With `--apply --publish`, commit and publish the draft. |

## Output And Logging

Normal CLI output is intentionally minimal: selected version ids, planned draft name/description, target draft id/name when created, ZIP size, and publish status. It does not print full API responses.

Set `VISIER_SDLC_DEBUG=1` only while troubleshooting draft metadata. Debug logging still avoids request credentials and full response dumps.

## API References

- [Production versions](https://docs.visier.com/developer/apis/administration/production-versions/code-samples.htm)
- [Projects](https://docs.visier.com/developer/apis/administration/projects/fundamentals/code-samples.htm)
