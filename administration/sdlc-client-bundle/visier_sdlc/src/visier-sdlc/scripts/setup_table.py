"""Create the state table before deploying an app that references it as a resource."""
import os
from pathlib import Path
import re
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState


def setup_table(workspace, env):
    for key in ("CATALOG", "SCHEMA", "TABLE"):
        if not re.fullmatch(r"[A-Za-z_]\w*", env[key]):
            raise ValueError(f"{key} must be a simple identifier")
    statement = (Path(__file__).resolve().parents[3] / "sql/init_tables.sql").read_text(encoding="utf-8")
    parameters = [StatementParameterListItem(name=key.lower(), value=env[key], type="STRING")
                  for key in ("CATALOG", "SCHEMA", "TABLE")]
    response = workspace.statement_execution.execute_statement(
        statement=statement, warehouse_id=env["WAREHOUSE_ID"], parameters=parameters, wait_timeout="30s")
    statement_id = response.statement_id
    while response.status and response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(1)
        response = workspace.statement_execution.get_statement(statement_id)
    if not response.status or response.status.state != StatementState.SUCCEEDED:
        raise RuntimeError("State table setup failed; inspect the SQL warehouse statement history")


if __name__ == "__main__":
    setup_table(WorkspaceClient(), os.environ)
