from __future__ import annotations

import os
from urllib.parse import urlsplit

import click
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from promotion.credentials import EnvironmentCredentials
from promotion.demo import DemoGateway
from promotion.ports import AppError
from promotion.service import DEFAULT_PROJECT_NAME, PromotionService
from promotion.storage import SQLiteStateStore
from promotion.visier import VisierGateway


def tenant_pair_key(credentials):
    import hashlib
    import json
    identity = [{k: v for k, v in credentials.configuration(role).items() if k in ("host", "tenant_id", "vanity")} for role in ("source", "target")]
    if identity[0] == identity[1]:
        raise ValueError("Source and target must be different tenants")
    return "live:" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def public_origin() -> str:
    """External origin for same-origin checks: PUBLIC_ORIGIN override, else Databricks Apps' DATABRICKS_APP_URL."""
    raw = os.getenv("PUBLIC_ORIGIN") or os.getenv("DATABRICKS_APP_URL", "")
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    return f"{parts.scheme}://{parts.netloc}"


def create_app(config=None, *, store=None, credentials=None, gateway=None):
    load_dotenv()
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(APP_MODE=os.getenv("APP_MODE", "demo"), STATE_DB=os.getenv("STATE_DB", "instance/promotion.sqlite3"),
                      PUBLIC_ORIGIN=public_origin(), MAX_CONTENT_LENGTH=16384)
    app.config.update(config or {})
    mode = app.config["APP_MODE"]
    if mode not in ("demo", "live"):
        raise ValueError("APP_MODE must be demo or live")
    credentials = credentials or EnvironmentCredentials()
    if mode == "live":
        pair = tenant_pair_key(credentials)
    else:
        pair = "demo"
    store = store or SQLiteStateStore(app.config["STATE_DB"], pair)
    gateway = gateway or (DemoGateway(store) if mode == "demo" else VisierGateway(credentials))
    initial_source, initial_target = os.getenv("INITIAL_SOURCE_VERSION_ID"), os.getenv("INITIAL_TARGET_VERSION_ID")
    if mode == "live" and (initial_source or initial_target):
        if not (initial_source and initial_target):
            raise ValueError("Both initial checkpoint IDs are required")
        revision, state = store.read()
        if not state.get("checkpoint"):
            state["checkpoint"] = dict(source_id=initial_source, target_id=initial_target, at=None)
            state["managed_target_ids"] = [initial_target]
            store.compare_and_swap(revision, state)
    service = PromotionService(gateway, store, os.getenv("SOURCE_NAME", "Development"), os.getenv("TARGET_NAME", "Production"), mode)
    app.extensions["promotion"] = service
    connections = {}
    for role in ("source", "target"):
        configuration = credentials.configuration(role) if mode == "live" else {}
        # Only these display fields may be sent to the browser.
        connections[role] = {field: configuration.get(field) for field in ("vanity", "host", "username")}

    @app.before_request
    def same_origin_writes():
        if request.method == "POST":
            expected_origin = app.config["PUBLIC_ORIGIN"] or request.host_url.rstrip("/")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (request.headers.get("Origin") and request.headers["Origin"] != expected_origin):
                raise AppError("Cross-origin operations are not allowed.", 403)
            if not request.is_json:
                raise AppError("Send an application/json request.", 415)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/state")
    def get_state():
        return jsonify(dict(service.snapshot(), connections=connections))

    @app.post("/api/sync")
    def sync():
        data = request.get_json()
        if not isinstance(data, dict) or not isinstance(data.get("version_id"), str) or not isinstance(data.get("fingerprint"), str):
            raise AppError("A version ID and state fingerprint are required.", 400)
        return jsonify(service.run("sync", data["fingerprint"], data["version_id"],
                                   project_name=data.get("project_name", DEFAULT_PROJECT_NAME),
                                   project_description=data.get("project_description", "")))

    @app.post("/api/rollback")
    def rollback():
        data = request.get_json()
        if not isinstance(data, dict) or not isinstance(data.get("fingerprint"), str):
            raise AppError("A state fingerprint is required.", 400)
        return jsonify(service.run("rollback", data["fingerprint"]))

    @app.post("/api/sources/migrate")
    def migrate_sources():
        data = request.get_json()
        if not isinstance(data, dict) or not isinstance(data.get("fingerprint"), str):
            raise AppError("A state fingerprint is required.", 400)
        return jsonify(service.migrate_sources(data["fingerprint"],
                                              replace_all_existing_sources=data.get("replace_all_existing_sources", False)))

    @app.post("/api/rebaseline")
    def rebaseline():
        data = request.get_json()
        if not isinstance(data, dict) or not isinstance(data.get("fingerprint"), str):
            raise AppError("A state fingerprint is required.", 400)
        return jsonify(service.rebaseline(data["fingerprint"], source_id=data.get("source_id"),
                                          target_id=data.get("target_id"), reason=data.get("reason"),
                                          verified=data.get("verified")))

    @app.post("/api/operations/recover")
    def recover_operation():
        data = request.get_json()
        if (not isinstance(data, dict) or not isinstance(data.get("operation_id"), str)
                or type(data.get("state_revision")) is not int or not isinstance(data.get("action"), str)):
            raise AppError("An operation ID, state revision, and recovery action are required.", 400)
        return jsonify(service.recover(data["operation_id"], data["state_revision"], data["action"],
                                       verified=data.get("verified"), target_id=data.get("target_id")))

    @app.post("/api/demo/drift")
    def demo_drift():
        if mode != "demo":
            raise AppError("Demo controls are unavailable in live mode.", 404)
        gateway.add_drift()
        return jsonify(message="A direct production change was added to the demo.")

    @app.errorhandler(AppError)
    def domain_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(Exception)
    def server_error(error):
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        # Do not log raw SDK exception payloads or credential-bearing headers.
        app.logger.error("Request failed: %s", type(error).__name__)
        return jsonify(error="Unable to read tenant data. Verify the server configuration and tenant access, then refresh."), 502

    @app.cli.command("reconcile")
    @click.option("--target-version-id", help="Production version confirmed to have been published by the unresolved operation")
    @click.option("--not-published", is_flag=True, help="Confirm after inspection that the unresolved operation was never published")
    @click.option("--sources-imported", is_flag=True, help="Confirm after inspection that the target sources were imported")
    @click.option("--not-imported", is_flag=True, help="Confirm after inspection that the source import did not complete")
    def reconcile(target_version_id, not_published, sources_imported, not_imported):
        if sum(bool(option) for option in (target_version_id, not_published, sources_imported, not_imported)) != 1:
            raise click.UsageError("Choose exactly one of --target-version-id, --not-published, --sources-imported or --not-imported")
        service.reconcile(target_version_id, not_published, sources_imported=sources_imported, not_imported=not_imported)
        click.echo("Operation reconciled. Refresh the app.")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.getenv("PORT", "5050")), debug=False)
