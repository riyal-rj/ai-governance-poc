-- Establishes the `app` schema that owns every FinAssist-managed table.
-- `scripts/migrate.py` creates `app.schema_migrations` itself before applying
-- any file here, so this migration only needs to create the schema.
CREATE SCHEMA IF NOT EXISTS app;
