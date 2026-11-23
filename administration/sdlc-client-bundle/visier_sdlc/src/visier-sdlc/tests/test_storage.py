import subprocess
import sys
from pathlib import Path

import pytest

from promotion.storage import qualified_table_name


def test_table_name_is_qualified_with_configured_catalog_and_schema():
    assert qualified_table_name("test_catalog", "app_schema", "custom_state") == "test_catalog.app_schema.custom_state"


@pytest.mark.parametrize("component", range(3))
@pytest.mark.parametrize("invalid", ["", "catalog.schema.table", "schema.table", "bad;name", "bad name", "1name"])
def test_table_name_components_must_be_unqualified_identifiers(component, invalid):
    parts = ["test_catalog", "app_schema", "promotion_state"]
    parts[component] = invalid
    with pytest.raises(ValueError, match="Expected an unqualified"):
        qualified_table_name(*parts)


@pytest.mark.skipif(sys.platform == "win32", reason="Requires POSIX file descriptor limits")
def test_sqlite_operations_do_not_exhaust_file_handles(tmp_path):
    # Isolate the descriptor limit and disabled GC from pytest itself. This
    # reproduces the leak even on machines with a very high default file limit.
    script = """
import gc
import resource
import sys

from promotion.ports import AppError
from promotion.storage import SQLiteStateStore

_, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
limit = 64 if hard == resource.RLIM_INFINITY else min(64, hard)
resource.setrlimit(resource.RLIMIT_NOFILE, (limit, hard))
gc.disable()
for index in range(200):
    store = SQLiteStateStore(sys.argv[1], "test")
    revision, state = store.read()
    store.compare_and_swap(revision, {"index": index})
    try:
        store.compare_and_swap(revision, {"index": "stale"})
    except AppError:
        pass
    else:
        raise AssertionError("Stale update was accepted")
    assert store.read() == (revision + 1, {"index": index})
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "state.sqlite3")],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
