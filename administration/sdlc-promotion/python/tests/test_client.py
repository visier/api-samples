from __future__ import annotations

import unittest
from types import SimpleNamespace

from visier_sdlc.client import VisierClient, _safe_api_error_message
from visier_sdlc.exceptions import VisierSDLCError


class _FakeProductionVersionsApi:
    def __init__(self, response: object) -> None:
        self.response = response

    def post_production_versions_without_preload_content(self, *_args, **_kwargs):
        return self.response


class _FakeOperationType:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class ClientTests(unittest.TestCase):
    def _client_with_export_response(self, response: object) -> VisierClient:
        client = object.__new__(VisierClient)
        client._profile = SimpleNamespace(target_tenant_id=None)
        client._timeout = 120
        client._production_versions_api = _FakeProductionVersionsApi(response)
        client._production_versions_operation_type = _FakeOperationType
        client._export_params_type = _FakeOperationType
        client._api_exception_type = RuntimeError
        return client

    def test_export_rejects_empty_body(self) -> None:
        client = self._client_with_export_response(
            SimpleNamespace(headers={"Content-Type": "application/zip"}, data=b"")
        )

        with self.assertRaisesRegex(VisierSDLCError, "response body was empty"):
            client.export_production_versions_zip("start", "end")

    def test_export_rejects_non_zip_body(self) -> None:
        client = self._client_with_export_response(
            SimpleNamespace(headers={"Content-Type": "application/octet-stream"}, data=b"not-a-zip")
        )

        with self.assertRaisesRegex(VisierSDLCError, "ZIP signature"):
            client.export_production_versions_zip("start", "end")

    def test_export_accepts_zip_signature_with_generic_content_type(self) -> None:
        client = self._client_with_export_response(
            SimpleNamespace(headers={"Content-Type": "application/octet-stream"}, data=b"PK\x03\x04zip")
        )

        with self.assertLogs("visier_sdlc.client", level="WARNING"):
            self.assertEqual(client.export_production_versions_zip("start", "end"), b"PK\x03\x04zip")

    def test_safe_api_error_message_redacts_secret_fields(self) -> None:
        exc = SimpleNamespace(
            status=400,
            reason="Bad Request",
            data='{"password":"secret","apiKey":"abc","access_token":"tok","message":"invalid"}',
        )

        message = _safe_api_error_message(exc)

        self.assertIn("HTTP 400", message)
        self.assertIn('"password":"<redacted>"', message)
        self.assertIn('"apiKey":"<redacted>"', message)
        self.assertIn('"access_token":"<redacted>"', message)
        self.assertNotIn("secret", message)
        self.assertNotIn("abc", message)
        self.assertNotIn(':"tok"', message)


if __name__ == "__main__":
    unittest.main()
