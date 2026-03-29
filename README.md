# prover-poslance

ETL pipeline that downloads Czech Parliament (PSP) open data from [psp.cz](https://www.psp.cz/sqw/hp.sqw?k=1300), parses it, and loads it into a database (local SQLite or [Turso](https://turso.tech)).

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
uv sync
cp .env.example .env   # then fill in your credentials
```

### Database options

**Local SQLite** (default, no config needed):

```bash
uv run python etl_script.py --term 9
```

The database is created at `~/.prover-poslance/tmp/parliament_data.db`.

**Turso** (remote, recommended for the website):

```bash
# Install the Turso CLI and create a database
turso db create prover-poslance

# Get your credentials
turso db show --url prover-poslance
turso db tokens create prover-poslance --expiration none
```

Add them to `.env`:

```
TURSO_DATABASE_URL=libsql://your-db-yourorg.turso.io
TURSO_AUTH_TOKEN=your-token
```

## Usage

```bash
# List available parliamentary terms
uv run python etl_script.py --list-terms

# Load current (9th) term only
uv run python etl_script.py --term 9

# Load multiple terms
uv run python etl_script.py --term 8 9

# Load all terms (no filter)
uv run python etl_script.py

# Delete extracted files after loading to save disk space
uv run python etl_script.py --term 9 --cleanup
```

### CLI reference

| Flag | Description |
|------|-------------|
| `--term N [N ...]` | Only load data for these electoral terms. Shared reference data (osoby, organy) is always included. |
| `--list-terms` | Print available terms and exit. |
| `--db-url URL` | Database URL. Overrides env vars. Accepts a local SQLite path or a `libsql://` Turso URL. |
| `--temp-dir DIR` | Directory for downloaded ZIPs and schema pages. Default: `~/.prover-poslance/tmp`. |
| `--schema-file PATH` | Output path for generated SQL schema. Default: `schema.sql`. |
| `--cleanup` | Delete extracted `.unl` files after each ZIP is loaded. |

### Environment variables

| Variable | Description |
|----------|-------------|
| `TURSO_DATABASE_URL` | Turso connection URL (`libsql://...`). Takes priority over `DATABASE_URL`. |
| `TURSO_AUTH_TOKEN` | Auth token for Turso. Required when using a `libsql://` URL. |
| `DATABASE_URL` | SQLite file path. Fallback if `TURSO_DATABASE_URL` is not set. |
| `ETL_TEMP_DIR` | Override the default temp directory (`~/.prover-poslance/tmp`). |

## CI / GitHub Actions

The workflow at `.github/workflows/etl.yml` runs the ETL automatically.

### Triggers

| Trigger | Behavior |
|---------|----------|
| **Schedule** — every Sunday 02:00 UTC | Runs current term only (`--term 10`) |
| **Manual** (`workflow_dispatch`) | Runs current term by default; set `full_sync: true` for all terms |

### Setup (one-time)

Add the two Turso credentials as repository secrets:

```bash
gh secret set TURSO_DATABASE_URL --body "libsql://your-db.turso.io"
gh secret set TURSO_AUTH_TOKEN   # paste token interactively
```

### Running manually

```bash
# Current term only
gh workflow run etl.yml

# Full historical sync (all terms)
gh workflow run etl.yml -f full_sync=true

# Watch live logs
gh run watch

# List recent runs
gh run list --workflow=etl.yml
```

### Caching

The `~/.prover-poslance/tmp` directory is cached between runs. Combined with the ETag/hash skip logic in `etl_script.py`, this means unchanged ZIPs are never re-downloaded.

## How it works

```
psp.cz data page (hp.sqw?k=1300)
        |
        v
1. Discover ZIP URLs + schema doc URLs per term
        |
        v
2. Download schema HTML pages, parse <h2>Tabulka ... sections
   to build {table_name: [{name, type}, ...]} schema dict
        |
        v
3. Download + extract each ZIP (cached: skips if .unl files exist)
        |
        v
4. Parse .unl files (pipe-delimited, cp1250 encoding) into DataFrames
        |
        v
5. Upsert into database (INSERT ... ON CONFLICT DO UPDATE)
        |
        v
6. [Turso only] Sync local embedded replica to remote
```

## Data source

All data comes from the Czech Parliament open data portal:
**https://www.psp.cz/sqw/hp.sqw?k=1300**

Source files are pipe-delimited `.unl` files encoded in `cp1250`, distributed as ZIP archives. Schema documentation is in HTML pages linked from the data portal.

### Key table groups

| Group | Tables | Description |
|-------|--------|-------------|
| People | `osoby`, `poslanec`, `pkgps`, `osoba_extra` | MP identity, contact, GPS |
| Organization | `organy`, `typ_organu`, `funkce`, `typ_funkce`, `zarazeni` | Committees, parties, roles, membership |
| Voting | `hl_hlasovani`, `hl_poslanec`, `omluvy`, `zmatecne` | Votes per session, individual MP votes, absences |
| Bills | `tisky`, `predkladatel`, `tisky_za`, `navrh_podpis`, `hist`, `hist_vybory` | Parliamentary prints, authorship, legislative history |
| Sessions | `schuze`, `bod_schuze`, `bod_stav`, `schuze_stav` | Sessions, agenda items, status |
| Interpellations | `poradi`, `los_interpelaci`, `uitypv`, `ui_stav` | Oral questions to government |
| Speeches | `steno`, `steno_bod`, `rec` | Stenographic records, individual speech records |
| Legal | `sbirka`, `sb_pre`, `druh_predpisu` | Collection of laws |
| Senate | `se_tisk`, `psp2senat`, `se_druh_tisku` | Senate prints, cross-chamber links |

See [`erd.md`](erd.md) for the full entity-relationship diagram.
