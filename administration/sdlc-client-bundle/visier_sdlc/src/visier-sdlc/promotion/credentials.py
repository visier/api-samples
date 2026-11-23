from __future__ import annotations

import os


FIELDS = {
    "host": "HOST", "api_key": "APIKEY", "vanity": "VANITY",
    "username": "USERNAME", "password": "PASSWORD", "client_id": "CLIENT_ID",
    "client_secret": "CLIENT_SECRET", "access_token": "ACCESS_TOKEN",
    "asid_token": "ASID_TOKEN", "tenant_id": "TENANT_ID",
}


class EnvironmentCredentials:
    def configuration(self, role):
        return {field: os.environ[f"{role.upper()}_{suffix}"] for field, suffix in FIELDS.items() if os.environ.get(f"{role.upper()}_{suffix}")}


class DatabricksSecretsCredentials:
    """Pass dbutils.secrets.get (or another secret reader) from the app bootstrap."""

    def __init__(self, get_secret, scope: str, keys: dict):
        self.get_secret, self.scope, self.keys = get_secret, scope, keys

    def configuration(self, role):
        return {field: self.get_secret(scope=self.scope, key=key) for field, key in self.keys[role].items()}
