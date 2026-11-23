-- IDENTIFIER() lets Databricks safely bind catalog, schema and table names in DDL.
-- CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema);

CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema || '.' || :table) (
  pair STRING NOT NULL,
  revision BIGINT NOT NULL,
  document STRING NOT NULL
) USING DELTA;
