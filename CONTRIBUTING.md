# Contributing

Thanks for your interest in contributing to prověř-poslance.

## Project structure

```
etl_script.py   — ETL pipeline (Python, scrapes psp.cz → SQLite/Turso)
web/            — Next.js website (TypeScript, reads from the database)
```

## Local setup

### ETL

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python etl_script.py --term 10 --cleanup   # current term only, ~5 min
uv run python etl_script.py --list-terms           # see all available terms
```

No credentials needed — by default it writes to a local SQLite file at `~/.prover-poslance/tmp/parliament_data.db`.

### Website

Requires Node.js 18+.

```bash
cd web
npm install
cp .env.local.example .env.local   # point at your local SQLite or Turso DB
npm run dev                         # http://localhost:3000
```

The `.env.local.example` file shows the available variables. For local SQLite, leave `TURSO_DATABASE_URL` unset — the app falls back to the file the ETL wrote.

## Making changes

- **ETL changes** — run the ETL against a local SQLite DB to verify the data looks right. Check `schema.sql` is still consistent if you change table definitions.
- **Website changes** — `npm run build` in `web/` must pass (TypeScript + Next.js build) before submitting.
- **Both** — if you change the database schema, update both the ETL and the web queries.

## Submitting a pull request

1. Fork the repo and create a branch from `main`.
2. Keep PRs focused — one feature or fix per PR.
3. Make sure `npm run build` passes for web changes.
4. Describe what and why in the PR description, not just what the diff does.

## Data source

All parliamentary data comes from the [Czech Parliament open data portal](https://www.psp.cz/sqw/hp.sqw?k=1300) and is in the public domain.
