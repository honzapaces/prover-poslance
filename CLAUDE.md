# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ETL pipeline that scrapes Czech Parliament (PSP) open data from `psp.cz`, parses it, and loads it into a local SQLite database. The data covers members of parliament, voting records, parliamentary prints, sessions, stenographic records, and more.

## Setup and Running

This project uses `uv` for dependency management with Python 3.11.

```bash
# Install dependencies
uv sync

# Run the ETL script
uv run python etl_script.py
```

## Key Configuration

At the top of `etl_script.py`, three path constants need to be set before running:

- `TEMP_DIR` — directory for downloaded ZIPs and schema HTML files (currently hardcoded to a user-specific path)
- `EXTRACT_DIR` — subdirectory within `TEMP_DIR` for extracted files (auto-derived)
- `DB_NAME` — path for the output SQLite database (auto-derived)

## Architecture

The ETL pipeline follows this flow:

1. **Discover** — `get_zip_and_schema_urls()` scrapes `psp.cz/sqw/hp.sqw?k=1300` to find ZIP download links and their associated schema documentation pages.

2. **Schema extraction** — `get_all_schemas()` downloads each schema HTML page and calls `extract_schema_from_html()`, which parses `<h2>Tabulka ...` sections to build a `{table_name: [{name, type}, ...]}` schema dict. Voting tables (`hl_hlasovani`) get aliased to year-specific names (e.g. `hl2024s`, `hl2024h1`).

3. **Download & parse** — `download_and_extract_zip()` fetches each ZIP into a subdirectory. `parse_unl_file()` reads pipe-delimited `.unl` files using `pandas.read_csv` with `cp1250` encoding, then applies type coercions (int → Int64, dates → datetime).

4. **Load** — `load_to_sqlite()` creates tables via `create_table_with_pk()` using `PRIMARY_KEYS` dict, then does chunked `INSERT OR REPLACE` into SQLite. NaT/NaN values and datetime objects are normalized to strings/None for SQLite compatibility.

5. **Schema file** — `generate_sql_schema_file()` writes `schema.sql` from the dynamically extracted schema.

### Data Format

Source data is in `.unl` files (pipe-separated, `cp1250` encoding). Schema is documented in HTML pages on psp.cz. The `PRIMARY_KEYS` dict in the script defines composite and single-column PKs for each table.
