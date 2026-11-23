CREATE TABLE catalog.schema.promotion_state (
  pair STRING NOT NULL,
  revision BIGINT NOT NULL,
  document STRING NOT NULL
) USING DELTA;