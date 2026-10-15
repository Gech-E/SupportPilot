#!/bin/sh
# Runs once when the Postgres container initialises an empty data directory.
# Creates the restricted role the API uses at request time. The owner role (POSTGRES_USER)
# is used only by migrations. The app role cannot own tables or bypass row-level security.
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v dbname="$POSTGRES_DB" -v app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE supportpilot_app LOGIN PASSWORD :'app_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
GRANT CONNECT ON DATABASE :"dbname" TO supportpilot_app;
GRANT USAGE ON SCHEMA public TO supportpilot_app;
SQL
