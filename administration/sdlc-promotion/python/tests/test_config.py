from __future__ import annotations

import os
import tempfile
import unittest
import importlib.util
from pathlib import Path

from visier_sdlc.config import load_config


@unittest.skipUnless(importlib.util.find_spec("yaml"), "PyYAML is not installed")
class ConfigTests(unittest.TestCase):
    def test_load_config_rejects_same_source_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
profiles:
  source:
    base_url: "https://same.api.visier.io"
    api_key: "key"
    username: "user"
    password: "pass"
  target:
    base_url: "https://same.api.visier.io"
    api_key: "key"
    username: "user"
    password: "pass"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "same tenant"):
                load_config(path)

    def test_load_config_requires_https(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
profiles:
  source:
    base_url: "http://source.api.visier.io"
    api_key: "key"
    username: "user"
    password: "pass"
  target:
    base_url: "https://target.api.visier.io"
    api_key: "key"
    username: "user"
    password: "pass"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "https"):
                load_config(path)

    @unittest.skipUnless(importlib.util.find_spec("dotenv"), "python-dotenv is not installed")
    def test_env_file_loaded_only_from_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as cwd, tempfile.TemporaryDirectory() as cfg_dir:
            cwd_path = Path(cwd)
            cfg_path = Path(cfg_dir)
            (cwd_path / ".env").write_text("VISIER_SOURCE_PASSWORD=wrong\n", encoding="utf-8")
            (cfg_path / ".env").write_text("VISIER_SOURCE_PASSWORD=right\n", encoding="utf-8")
            config_file = cfg_path / "config.yaml"
            config_file.write_text(
                """
profiles:
  source:
    base_url: "https://source.api.visier.io"
    api_key: "key"
    username: "user"
    password: "${VISIER_SOURCE_PASSWORD}"
  target:
    base_url: "https://target.api.visier.io"
    api_key: "key"
    username: "user"
    password: "pass"
""",
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            old_env = os.environ.pop("VISIER_SOURCE_PASSWORD", None)
            try:
                os.chdir(cwd_path)
                cfg = load_config(config_file)
            finally:
                os.chdir(old_cwd)
                if old_env is not None:
                    os.environ["VISIER_SOURCE_PASSWORD"] = old_env
                else:
                    os.environ.pop("VISIER_SOURCE_PASSWORD", None)

            self.assertEqual(cfg["source"].password, "right")


if __name__ == "__main__":
    unittest.main()
