"""Create the state table before deploying an app that references it as a resource."""
import os
from pathlib import Path
import re
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState


def setup_table(workspace, env):
    names = {"catalog": env["BUNDLE_VAR_catalog_name"], "schema": env["BUNDLE_VAR_schema_name"],
             "table": env.get("BUNDLE_VAR_state_table_name", "promotion_state")}
    for key, value in names.items():
        if not re.fullmatch(r"[A-Za-z_]\w*", value):
            raise ValueError(f"{key} must be a simple identifier")
    statement = (Path(__file__).resolve().parents[3] / "sql/init_tables.sql").read_text(encoding="utf-8")
    parameters = [StatementParameterListItem(name=key, value=value, type="STRING")
                  for key, value in names.items()]
    response = workspace.statement_execution.execute_statement(
        statement=statement, warehouse_id=env["BUNDLE_VAR_warehouse_id"], parameters=parameters, wait_timeout="30s")
    statement_id = response.statement_id
    while response.status and response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(1)
        response = workspace.statement_execution.get_statement(statement_id)
    if not response.status or response.status.state != StatementState.SUCCEEDED:
        raise RuntimeError("State table setup failed; inspect the SQL warehouse statement history")


if __name__ == "__main__":
    setup_table(WorkspaceClient(), os.environ)
