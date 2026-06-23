-- Runs once on first Postgres init. Isolated DB for `docker compose exec app pytest`
-- so tests never touch local dev data.
CREATE DATABASE tolera_test;
