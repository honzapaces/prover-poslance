import argparse
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
import urllib.parse
import zipfile
import logging

from dotenv import load_dotenv
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://www.psp.cz"
DATA_PAGE_URL = f"{BASE_URL}/sqw/hp.sqw?k=1300"

TEMP_DIR = os.path.expanduser(os.environ.get("ETL_TEMP_DIR", "~/.prover-poslance/tmp"))
EXTRACT_DIR = os.path.join(TEMP_DIR, "extracted_data")
DB_NAME = (
    os.environ.get("TURSO_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or os.path.join(TEMP_DIR, "parliament_data.db")
)
SCHEMA_SQL_FILE = "schema.sql"
SCHEMA_MD_FILE  = "SCHEMA.md"

# Year-specific voting files use different schemas depending on the suffix:
#   s  → hl_hlasovani  (one row per vote session, 17 cols)
#   h1/h2/h3 → hl_poslanec (one row per MP per vote, 3 cols)
#   v  → hl_vazby      (vote–organ relationships, 3 cols)
#   x  → hl_zposlanec  (substitute votes, 3 cols)
#   z  → hl_check      (vote validation, 5 cols)
_HL_YEARS = range(1993, datetime.date.today().year + 1)
# hl_hlasovani session tables are kept year-specific (one per year) for efficient
# per-year queries. All other year-variant types (h1/h2/h3, v, x, z) are
# consolidated into their base table via _HL_FILE_REDIRECT below.
SCHEMA_ALIASES: dict[str, list[str]] = {
    "hl_hlasovani": [f"hlasovani_{y}s" for y in _HL_YEARS],
}

# Year-specific file variants (e.g. hl2021h1) should be consolidated into
# their base table instead of creating one table per year × suffix.
_HL_FILE_REDIRECT: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^hl\d{4}h\d$'), 'hlasovani_poslanec'),
    (re.compile(r'^hl\d{4}v$'),   'hlasovani_vazby'),
    (re.compile(r'^hl\d{4}x$'),   'hlasovani_zposlanec'),
    (re.compile(r'^hl\d{4}z$'),   'hlasovani_check'),
]

_HL_YEAR_SESSION_RE = re.compile(r'^hl(\d{4})s$')

# Maps original PSP table names (from HTML schema pages) to prefixed DB names.
TABLE_RENAME_MAP: dict[str, str] = {
    # People & Organisation
    "osoby":          "osoba_osoby",
    "poslanec":       "osoba_poslanec",
    "pkgps":          "osoba_pkgps",
    "zarazeni":       "osoba_zarazeni",
    "organy":         "osoba_organy",
    "typ_organu":     "osoba_typ_organu",
    "funkce":         "osoba_funkce",
    "typ_funkce":     "osoba_typ_funkce",
    # Voting
    "hl_hlasovani":   "hlasovani_session",
    "hl_poslanec":    "hlasovani_poslanec",
    "hl_zposlanec":   "hlasovani_zposlanec",
    "hl_vazby":       "hlasovani_vazby",
    "hl_check":       "hlasovani_check",
    "zmatecne":       "hlasovani_zmatecne",
    "omluvy":         "hlasovani_omluvy",
    # Bills (Tisky)
    "tisky":          "tisk_tisky",
    "druh_tisku":     "tisk_druh",
    "stavy":          "tisk_stavy",
    "typ_stavu":      "tisk_typ_stavu",
    "typ_zakon":      "tisk_typ_zakon",
    "predkladatel":   "tisk_predkladatel",
    "navrh_podpis":   "tisk_navrh_podpis",
    "tisky_za":       "tisk_za",
    "tz_eklep":       "tisk_tz_eklep",
    "hist":           "tisk_hist",
    "hist_vybory":    "tisk_hist_vybory",
    "vysledek":       "tisk_vysledek",
    "prechody":       "tisk_prechody",
    "sbirka":         "tisk_sbirka",
    "sb_pre":         "tisk_sb_pre",
    # Sessions (Schůze)
    "schuze":         "schuze_schuze",
    "bod_schuze":     "schuze_bod",
    "bod_stav":       "schuze_bod_stav",
    # Interpellations
    "los_interpelaci":"interpelace_los",
    "poradi":         "interpelace_poradi",
    "uitypv":         "interpelace_typ",
    "ui_stav":        "interpelace_stav",
    # Speeches & Stenography
    "steno":          "steno_steno",
    "rec":            "steno_rec",
    "se_tisk":        "steno_se_tisk",
    "se_druh_tisku":  "steno_se_druh",
    "psp2senat":      "steno_psp2senat",
    # Lookup / Reference
    "typ_akce":       "ref_typ_akce",
    "sd_dokument":    "ref_sd_dokument",
    "druh_predpisu":  "ref_druh_predpisu",
}


def _resolve_table(name: str) -> str:
    """Map a filename-derived table name to its final DB table name."""
    for pattern, target in _HL_FILE_REDIRECT:
        if pattern.match(name):
            return target
    m = _HL_YEAR_SESSION_RE.match(name)
    if m:
        return f"hlasovani_{m.group(1)}s"
    return TABLE_RENAME_MAP.get(name, name)


def _rename_schema_keys(schema: dict) -> dict:
    """Rename dynamic_schema keys from PSP names to prefixed DB names."""
    return {TABLE_RENAME_MAP.get(k, k): v for k, v in schema.items()}

PRIMARY_KEYS = {
    # People & Organisation
    "osoba_osoby":        ["id_osoba"],
    "osoba_funkce":       ["id_funkce"],
    "osoba_organy":       ["id_organ"],
    "osoba_typ_funkce":   ["id_typ_funkce"],
    "osoba_typ_organu":   ["id_typ_org"],
    "osoba_zarazeni":     ["id_osoba", "id_of", "od_o"],
    "osoba_poslanec":     ["id_poslanec"],
    "osoba_pkgps":        ["id_poslanec"],
    "osoba_extra":        ["id_osoba", "id_org", "typ"],
    # Voting
    "hlasovani_session":  ["id_hlasovani"],
    "hlasovani_zmatecne": ["id_hlasovani"],
    "hlasovani_omluvy":   ["id_organ", "id_poslanec", "den"],  # od (time) can be NULL — excluded from PK
    "hlasovani_poslanec": ["id_poslanec", "id_hlasovani"],
    "hlasovani_check":    ["id_hlasovani", "turn"],   # cols: id_hlasovani, turn, mode, id_h2, id_h3
    "hlasovani_zposlanec":["id_hlasovani", "id_osoba"], # cols: id_hlasovani, id_osoba, mode
    "hlasovani_vazby":    ["id_hlasovani", "turn"],     # cols: id_hlasovani, turn, typ
    # Bills (Tisky)
    "tisk_druh":          ["id_druh"],
    "tisk_typ_zakon":     ["id_navrh"],
    "tisk_typ_stavu":     ["id_typ"],
    "tisk_stavy":         ["id_stav"],
    "ref_typ_akce":       ["id_akce"],
    "tisk_prechody":      ["id_prechod"],
    "tisk_tisky":         ["id_tisk"],
    "tisk_tz_eklep":      ["id_tisk", "cislo_za"],
    "tisk_hist":          ["id_hist"],
    "tisk_za":            ["id_tisk", "cislo_za"],
    "tisk_vysledek":      ["id_vysledek"],
    "tisk_eklep":         ["id_tisk", "cislo_za"],
    "tisk_hist_vybory":   ["id_hist"],
    "tisk_predkladatel":  ["id_tisk", "id_osoba"],
    "tisk_navrh_podpis":  ["id_tisk", "id_osoba"],
    "tisk_sbirka":        ["id_sbirka"],
    "tisk_sb_pre":        ["id_tisk", "id_sbirka"],
    # Sessions (Schůze)
    "schuze_schuze":      ["id_schuze"],
    "schuze_bod":         ["id_schuze", "id_bod"],
    "schuze_bod_stav":    ["id_bod_stav"],
    "schuze_stav":        ["id_schuze", "stav"],
    # Interpellations
    "interpelace_typ":    ["id_ui_stav"],
    "interpelace_los":    ["id_los"],
    "interpelace_poradi": ["id_poradi"],
    "interpelace_stav":   ["id_poradi", "id_typ"],
    # Lookup / Reference
    "ref_sd_dokument":    ["id_dokument"],
    "ref_druh_predpisu":  ["id_dp"],
    # Speeches & Stenography
    "steno_steno":        ["id_steno"],
    "steno_bod":          ["id_steno", "aname"],
    "steno_rec":          ["id_steno", "aname"],
    "steno_se_tisk":      ["id_tisk"],
    "steno_psp2senat":    ["id_psp", "id_senat"],
    "steno_se_druh":      ["id_druh"],
}
# Year-specific session tables (hlasovani_2021s, hlasovani_2022s, …) share the hlasovani_session PK.
# They are kept as separate tables for per-year queries rather than consolidated.
for _y in _HL_YEARS:
    PRIMARY_KEYS[f"hlasovani_{_y}s"] = ["id_hlasovani"]

# ── Domain groupings for SCHEMA.md ───────────────────────────────────────────
TABLE_GROUPS: dict[str, list[str]] = {
    "People & Organisation": [
        "osoba_osoby", "osoba_poslanec", "osoba_pkgps", "osoba_zarazeni", "osoba_extra",
        "osoba_organy", "osoba_typ_organu", "osoba_funkce", "osoba_typ_funkce",
    ],
    "Voting": [
        "hlasovani_session", "hlasovani_poslanec", "hlasovani_zposlanec", "hlasovani_vazby",
        "hlasovani_check", "hlasovani_zmatecne", "hlasovani_omluvy",
    ],
    "Bills (Tisky)": [
        "tisk_tisky", "tisk_druh", "tisk_stavy", "tisk_typ_stavu", "tisk_typ_zakon",
        "tisk_predkladatel", "tisk_navrh_podpis", "tisk_za", "tisk_eklep", "tisk_tz_eklep",
        "tisk_hist", "tisk_hist_vybory", "tisk_vysledek", "tisk_prechody", "tisk_sbirka", "tisk_sb_pre",
    ],
    "Sessions (Schůze)": [
        "schuze_schuze", "schuze_bod", "schuze_bod_stav", "schuze_stav",
    ],
    "Interpellations": [
        "interpelace_los", "interpelace_poradi", "interpelace_typ", "interpelace_stav",
    ],
    "Speeches & Stenography": [
        "steno_steno", "steno_bod", "steno_rec", "steno_se_tisk", "steno_se_druh", "steno_psp2senat",
    ],
    "Lookup / Reference": [
        "ref_typ_akce", "ref_sd_dokument", "ref_druh_predpisu",
    ],
}

TABLE_DESCRIPTIONS: dict[str, str] = {
    # People & Organisation
    "osoba_osoby":         "Physical persons (MPs, ministers, substitutes).",
    "osoba_poslanec":      "MP record for one parliamentary term. One person → many rows across terms.",
    "osoba_pkgps":         "Constituency GPS coordinates for each MP.",
    "osoba_zarazeni":      "Club/committee membership intervals for a person.",
    "osoba_extra":         "Extra external IDs or URLs for a person (e.g. social media).",
    "osoba_organy":        "Parliamentary bodies: chambers, committees, clubs, governments.",
    "osoba_typ_organu":    "Lookup: body type (chamber, committee, club, …).",
    "osoba_funkce":        "Named roles within a body (Chairman, Deputy, …).",
    "osoba_typ_funkce":    "Lookup: function category.",
    # Voting
    "hlasovani_session":   "One row per vote session. Also used as schema for hlasovani_<YEAR>s tables.",
    "hlasovani_poslanec":  "Individual MP vote result for one session. `vysledek` codes: A=yes, B/N=no, C=abstain, F=registered but did not vote, @=absent, M=excused (omluven), W=before oath, K=abstain variant.",
    "hlasovani_zposlanec": "Substitute MP vote records.",
    "hlasovani_vazby":     "Links a vote session to additional organs.",
    "hlasovani_check":     "Vote integrity / validation metadata.",
    "hlasovani_zmatecne":  "Flags a vote session as procedurally void.",
    "hlasovani_omluvy":    "Formal advance excuse filed by an MP for a specific day. `od`/`do` = time range (nullable).",
    # Bills (Tisky)
    "tisk_tisky":          "Parliamentary prints (bills, reports, petitions, …).",
    "tisk_druh":           "Lookup: print type.",
    "tisk_stavy":          "Lookup: bill status codes.",
    "tisk_typ_stavu":      "Lookup: status type.",
    "tisk_typ_zakon":      "Lookup: law type.",
    "tisk_predkladatel":   "Primary submitter(s) of a bill.",
    "tisk_navrh_podpis":   "Co-signatories of a bill.",
    "tisk_za":             "Bill versions / amendments.",
    "tisk_eklep":          "EKLEP (government legislative plan) entries linked to prints.",
    "tisk_tz_eklep":       "EKLEP entries linked to bill versions.",
    "tisk_hist":           "Legislative history events for a bill.",
    "tisk_hist_vybory":    "Committee participation in a history event.",
    "tisk_vysledek":       "Lookup: legislative result codes.",
    "tisk_prechody":       "Lookup: legislative transition labels.",
    "tisk_sbirka":         "Published law collection entries.",
    "tisk_sb_pre":         "Links a collection entry to its source prints.",
    # Sessions (Schůze)
    "schuze_schuze":       "Plenary session (schůze) header.",
    "schuze_bod":          "Agenda item within a session.",
    "schuze_bod_stav":     "Lookup: agenda item status.",
    "schuze_stav":         "Status history of a session.",
    # Interpellations
    "interpelace_los":     "Interpellation lottery draw session.",
    "interpelace_poradi":  "Ordered interpellation within a lottery.",
    "interpelace_typ":     "Interpellation type assignment.",
    "interpelace_stav":    "Status of an interpellation.",
    # Speeches & Stenography
    "steno_steno":         "Stenographic session header.",
    "steno_bod":           "Stenographic record for one agenda item.",
    "steno_rec":           "Individual speech record (speaker + session + item).",
    "steno_se_tisk":       "Senate print cross-reference.",
    "steno_se_druh":       "Senate print type lookup.",
    "steno_psp2senat":     "Mapping from Chamber print to Senate equivalent.",
    # Lookup / Reference
    "ref_typ_akce":        "Lookup: action type.",
    "ref_sd_dokument":     "Shared document metadata.",
    "ref_druh_predpisu":   "Lookup: regulation type.",
}


def connect_db(db_url: str, temp_dir: str):
    """Return a DB-API connection to either Turso (libsql) or local SQLite."""
    if db_url.startswith("libsql://"):
        try:
            import libsql
        except ImportError:
            raise ImportError("Install the Turso driver first: uv add libsql")
        auth_token = os.environ.get("TURSO_AUTH_TOKEN")
        if not auth_token:
            raise ValueError("TURSO_AUTH_TOKEN env var is required for Turso connections.")
        cache_path = os.path.join(temp_dir, "turso_cache.db")
        logger.info(f"Connecting to Turso: {db_url}  (local cache: {cache_path})")
        conn = libsql.connect(cache_path, sync_url=db_url, auth_token=auth_token)
        conn.sync()
        return conn
    else:
        logger.info(f"Connecting to SQLite: {db_url}")
        return sqlite3.connect(db_url)


def psp_type_to_sql(col_type: str) -> str:
    """Map a PSP column type string to a SQL type."""
    if "int" in col_type:
        return "INTEGER"
    if "date" in col_type:
        return "TEXT"  # stored as ISO-formatted string
    return "TEXT"


def _normalize_df_for_db(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized conversion of a DataFrame to DB-safe types (None, str, number)."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        elif df[col].dtype == 'object':
            # Convert any datetime.time or other non-string objects to str
            df[col] = df[col].map(
                lambda x: str(x) if x is not None and hasattr(x, 'strftime') else x
            )
        # Replace all NaN/NaT/pd.NA variants with Python None.
        #
        # Why .astype(object) first:
        # Pandas nullable integer columns (Int64) use pd.NA as their missing-value
        # sentinel. Calling .where(cond, None) on an Int64 Series does NOT produce
        # Python None — pandas coerces the replacement back to pd.NA to preserve the
        # dtype. The sqlite3 driver cannot bind pd.NA and raises:
        #   "Error binding parameter N: type 'NAType' is not supported"
        # Converting to object dtype first breaks the dtype constraint, so the
        # subsequent .where() can store a real Python None, which sqlite3 maps to NULL.
        df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def extract_schema_from_html(html_file_path: str) -> dict:
    """Extract schema definitions from a PSP HTML documentation page."""
    logger.info(f"Extracting schema from {html_file_path}...")
    try:
        with open(html_file_path, 'r', encoding='cp1250') as f:
            soup = BeautifulSoup(f, 'html.parser')
    except FileNotFoundError:
        logger.error(f"Schema HTML file not found: {html_file_path}")
        return {}
    except Exception as e:
        logger.error(f"Error reading or parsing schema HTML file {html_file_path}: {e}")
        return {}

    dynamic_schema = {}

    for h2_tag in soup.find_all('h2'):
        if not h2_tag.text.strip().startswith('Tabulka '):
            continue
        unl_file_key = h2_tag.text.strip().replace('Tabulka ', '').lower()

        table_tag = h2_tag.find_next_sibling('table')
        if not table_tag:
            continue

        all_trs = table_tag.find_all('tr')
        first_td = all_trs[0].find('td') if all_trs else None
        start_row_index = 1 if (first_td and 'Sloupec' in first_td.text) else 0

        current_table_schema = [
            {"name": cols[0].text.strip(), "type": cols[1].text.strip()}
            for tr in all_trs[start_row_index:]
            if len(cols := tr.find_all('td')) >= 2
        ]

        if not current_table_schema:
            continue

        # Some PSP schema pages document two tables under a single <h2>, e.g.
        # "Tabulka tisk_eklep, tz_eklep".  Register the schema under each name.
        for key in [k.strip() for k in unl_file_key.split(',')]:
            dynamic_schema[key] = current_table_schema
            for alias in SCHEMA_ALIASES.get(key, []):
                dynamic_schema[alias] = current_table_schema

    logger.info(f"Schema extraction completed for {html_file_path}.")
    return dynamic_schema


def download_and_extract_zip(
    zip_url: str,
    extract_to_dir: str,
    zip_state: dict,
    force: bool = False,
) -> tuple[str | None, bool]:
    """Download a ZIP and extract to extract_to_dir.

    Returns (extract_to_dir | None, data_was_new).
    data_was_new=False means the ZIP is unchanged and already loaded to DB — skip DB load.
    zip_state is mutated in place with updated ETag/hash for the URL.
    """
    url_state = zip_state.get(zip_url, {})

    if url_state and not force:
        try:
            head = requests.head(zip_url, timeout=10)
            head.raise_for_status()
            server_etag = head.headers.get("ETag")
            server_lm = head.headers.get("Last-Modified")

            if server_etag and server_etag == url_state.get("etag"):
                if url_state.get("processed_at"):
                    logger.info(f"Skipping {zip_url} — ETag unchanged, data already in DB.")
                    return extract_to_dir, False

            elif (not server_etag) and server_lm and server_lm == url_state.get("last_modified"):
                if url_state.get("processed_at"):
                    logger.info(f"Skipping {zip_url} — Last-Modified unchanged, data already in DB.")
                    return extract_to_dir, False

        except requests.exceptions.RequestException as e:
            logger.warning(f"HEAD request for {zip_url} failed ({e}), falling back to full download.")

    has_unl = os.path.isdir(extract_to_dir) and any(f.endswith('.unl') for f in os.listdir(extract_to_dir))
    if has_unl and not force:
        if url_state.get("processed_at"):
            logger.info(f"Skipping {zip_url} — .unl files present and data already in DB.")
            return extract_to_dir, False
        logger.info(f".unl files present for {zip_url} but not yet processed; will load them.")
        return extract_to_dir, True

    logger.info(f"Downloading {zip_url}...")
    try:
        response = requests.get(zip_url, timeout=300)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download {zip_url}: {e}")
        return None, False

    content_sha256 = hashlib.sha256(response.content).hexdigest()

    # Hash-based skip: server gave us no useful headers but content is identical
    if not force and url_state.get("content_sha256") == content_sha256 and url_state.get("processed_at"):
        logger.info(f"Skipping {zip_url} — content hash unchanged, data already in DB.")
        # Update headers in state since they apparently drifted
        zip_state[zip_url] = {
            **url_state,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "content_sha256": content_sha256,
        }
        return extract_to_dir, False

    try:
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path) as zip_ref:
            zip_ref.extractall(extract_to_dir)
        os.unlink(tmp_path)
    except zipfile.BadZipFile:
        logger.error(f"Downloaded file is not a valid ZIP file: {zip_url}")
        return None, False
    except Exception as e:
        logger.error(f"Error extracting ZIP file {zip_url}: {e}")
        return None, False

    # Store ETag/hash; processed_at is set by caller after DB load
    zip_state[zip_url] = {
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "content_sha256": content_sha256,
        "processed_at": None,
    }
    logger.info(f"Extracted {zip_url} to {extract_to_dir}")
    return extract_to_dir, True


def parse_unl_file(file_path: str, schema_def: list) -> pd.DataFrame:
    logger.info(f"Parsing UNL file: {file_path}")
    column_names = [col["name"] for col in schema_def]

    try:
        df = pd.read_csv(
            file_path,
            sep='|',
            header=None,
            names=column_names,
            encoding='cp1250',
            dtype=str,
            na_values=[''],
            usecols=range(len(column_names)),  # ignore extra columns from trailing pipes
        )
    except FileNotFoundError:
        logger.error(f"UNL file not found: {file_path}")
        return pd.DataFrame()
    except pd.errors.ParserError as e:
        logger.error(f"Error parsing UNL file {file_path}: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"An unexpected error occurred while parsing {file_path}: {e}")
        return pd.DataFrame()

    for col_def in schema_def:
        col_name = col_def["name"]
        col_type = col_def["type"]
        if col_name not in df.columns:
            continue
        try:
            if "int" in col_type:
                df[col_name] = pd.to_numeric(df[col_name], errors='coerce').astype('Int64')
            elif "date" in col_type:
                if "datetime" in col_type:
                    if "second" in col_type:
                        df[col_name] = pd.to_datetime(df[col_name], format='%Y-%m-%d %H:%M:%S', errors='coerce')
                    elif "hour" in col_type:
                        if "year" in col_type:
                            df[col_name] = pd.to_datetime(df[col_name], format='%Y-%m-%d %H', errors='coerce')
                        else:
                            df[col_name] = pd.to_datetime(df[col_name], format='%H:%M', errors='coerce').dt.time
                else:
                    df[col_name] = pd.to_datetime(df[col_name], format='%d.%m.%Y', errors='coerce')
        except Exception as e:
            logger.warning(
                f"Failed to convert column '{col_name}' to type '{col_type}' "
                f"in file '{file_path}': {e}. Column will remain as string."
            )

    return df


def create_all_tables(dynamic_schema: dict, primary_keys: dict, conn) -> None:
    """Create all tables upfront before loading data."""
    for table_name, schema_def in dynamic_schema.items():
        columns_sql = [f"{col['name']} {psp_type_to_sql(col['type'])}" for col in schema_def]
        pk_cols = primary_keys.get(table_name, [])
        pk_constraint = f", PRIMARY KEY ({', '.join(pk_cols)})" if pk_cols else ""
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns_sql)}{pk_constraint});"
        try:
            conn.execute(sql)
        except Exception as e:
            logger.error(f"Error creating table '{table_name}': {e}")
    conn.commit()
    logger.info(f"Ensured {len(dynamic_schema)} tables exist.")


def load_to_db(
    df: pd.DataFrame,
    table_name: str,
    primary_keys: dict,
    conn,
    chunk_size: int = 10000,
) -> None:
    import time
    total_rows = len(df)
    logger.info(f"Loading data to table: {table_name} ({total_rows} rows)")
    if df.empty:
        logger.warning(f"DataFrame for {table_name} is empty. Skipping load.")
        return

    t_normalize = time.monotonic()
    df = _normalize_df_for_db(df)
    logger.debug(f"  {table_name}: normalize took {time.monotonic() - t_normalize:.2f}s")

    columns = ", ".join(df.columns)
    placeholders = ", ".join(["?" for _ in df.columns])
    pk_cols = primary_keys.get(table_name, [])
    if pk_cols:
        # Proper upsert: on conflict, update all non-PK columns
        non_pk_cols = [c for c in df.columns if c not in pk_cols]
        if non_pk_cols:
            update_clause = ", ".join(f"{c} = excluded.{c}" for c in non_pk_cols)
            insert_sql = (
                f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {update_clause};"
            )
        else:
            insert_sql = (
                f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT ({', '.join(pk_cols)}) DO NOTHING;"
            )
    else:
        insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders});"
        logger.warning(f"No primary key for '{table_name}'. INSERT may produce duplicates.")

    total_chunks = (total_rows + chunk_size - 1) // chunk_size
    t_start = time.monotonic()
    try:
        cursor = conn.cursor()
        for i in range(0, total_rows, chunk_size):
            chunk = df.iloc[i:i + chunk_size]
            chunk_num = i // chunk_size + 1
            t_chunk = time.monotonic()
            cursor.executemany(insert_sql, [tuple(row) for row in chunk.values])
            elapsed = time.monotonic() - t_chunk
            rows_done = min(i + chunk_size, total_rows)
            pct = rows_done / total_rows * 100
            logger.info(
                f"  {table_name}: chunk {chunk_num}/{total_chunks} "
                f"({rows_done}/{total_rows} rows, {pct:.0f}%) "
                f"chunk={elapsed:.2f}s total={time.monotonic() - t_start:.1f}s"
            )
        # Commit once per table — avoids per-chunk network round-trips to Turso
        conn.commit()
        logger.info(f"  {table_name}: done — {total_rows} rows in {time.monotonic() - t_start:.1f}s")
    except Exception as e:
        logger.error(f"Error loading data to table {table_name}: {e}")


def _extract_term_number(text: str) -> int | None:
    """Extract the term number from a row's text, e.g. '9. volební období' → 9."""
    match = re.search(r'(\d+)\.\s*volebn', text)
    return int(match.group(1)) if match else None


def get_zip_and_schema_urls(data_page_url: str) -> list[dict]:
    """Scrape the PSP data page and return [{zip_url, schema_doc_url, term}, ...] entries.

    'term' is the electoral term number (1–10) or None if it could not be detected.
    """
    logger.info(f"Fetching data page: {data_page_url}...")
    zip_schema_pairs = []
    try:
        response = requests.get(data_page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        data_table = soup.find('table', border="1")
        if not data_table:
            logger.warning(f"Could not find the main data table on {data_page_url}.")
            return zip_schema_pairs

        for tr in data_table.find_all('tr'):
            zip_link = tr.find('a', href=lambda h: h and h.endswith('.zip'))
            if not zip_link:
                continue
            zip_url = urllib.parse.urljoin(BASE_URL, zip_link['href'])

            schema_link = tr.find('a', href=lambda h: h and h.startswith('hp.sqw?k='))
            schema_doc_url = urllib.parse.urljoin(data_page_url, schema_link['href']) if schema_link else None

            term = _extract_term_number(tr.get_text())

            zip_schema_pairs.append({"zip_url": zip_url, "schema_doc_url": schema_doc_url, "term": term})

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch data page {data_page_url}: {e}")
    except Exception as e:
        logger.error(f"Error parsing data page HTML {data_page_url}: {e}")

    logger.info(f"Discovered {len(zip_schema_pairs)} ZIP file entries.")
    return zip_schema_pairs


def get_all_schemas(zip_schema_pairs: list[dict], temp_dir: str) -> dict:
    """Download schema HTML pages and return an aggregated schema dict."""
    logger.info("Aggregating schema definitions...")
    aggregated_schema: dict = {}
    seen_urls: set[str] = set()

    for entry in zip_schema_pairs:
        schema_doc_url = entry.get("schema_doc_url")
        if not schema_doc_url or schema_doc_url in seen_urls:
            continue
        seen_urls.add(schema_doc_url)

        parsed = urllib.parse.urlparse(schema_doc_url)
        basename = os.path.basename(parsed.path)
        filename = f"{basename}_{parsed.query}.html" if parsed.query else f"{basename}.html"
        html_path = os.path.join(temp_dir, filename)

        if not os.path.exists(html_path):
            try:
                response = requests.get(schema_doc_url)
                response.raise_for_status()
                with open(html_path, 'wb') as f:
                    f.write(response.content)
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download schema from {schema_doc_url}: {e}. Skipping.")
                continue

        aggregated_schema.update(extract_schema_from_html(html_path))

    logger.info(f"Aggregated schema: {len(aggregated_schema)} tables.")
    return aggregated_schema


def generate_sql_schema_file(dynamic_schema: dict, primary_keys: dict, output_file_path: str) -> None:
    """Write CREATE TABLE statements for all tables to a SQL file."""
    logger.info(f"Generating SQL schema file: {output_file_path}")
    with open(output_file_path, 'w', encoding='utf-8') as f:
        for table_name, schema_def in dynamic_schema.items():
            columns_sql = [f"{col['name']} {psp_type_to_sql(col['type'])}" for col in schema_def]
            pk_cols = primary_keys.get(table_name, [])
            pk_constraint = f", PRIMARY KEY ({', '.join(pk_cols)})" if pk_cols else ""
            f.write(f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns_sql)}{pk_constraint});\n")
    logger.info("SQL schema file generated.")


def generate_md_schema_file(dynamic_schema: dict, primary_keys: dict, output_file_path: str) -> None:
    """Write a navigable Markdown schema reference to output_file_path."""
    logger.info(f"Generating Markdown schema file: {output_file_path}")

    # Build the set of all grouped tables so we can catch unclassified ones.
    grouped: set[str] = {t for tables in TABLE_GROUPS.values() for t in tables}
    hl_year_set = {f"hlasovani_{y}s" for y in _HL_YEARS}
    hl_first = min(_HL_YEARS)
    hl_last  = max(_HL_YEARS)

    def _anchor(name: str) -> str:
        """GitHub-flavoured Markdown heading anchor (strips non-word chars, collapses spaces)."""
        lowered = name.lower()
        stripped = re.sub(r'[^\w\s-]', '', lowered)   # keep word chars, spaces, hyphens
        return re.sub(r'\s+', '-', stripped.strip())    # spaces → single hyphen

    def _table_section(table_name: str) -> list[str]:
        lines: list[str] = []
        lines.append(f"### {table_name}\n")
        desc = TABLE_DESCRIPTIONS.get(table_name)
        if desc:
            lines.append(f"{desc}\n")
        schema_def = dynamic_schema.get(table_name)
        if not schema_def:
            lines.append("_No columns found in dynamic schema._\n")
            return lines
        pk_cols = primary_keys.get(table_name, [])
        composite = len(pk_cols) > 1
        lines.append("| Column | Type | Notes |")
        lines.append("|--------|------|-------|")
        for col in schema_def:
            col_name = col["name"]
            col_type = psp_type_to_sql(col["type"])
            if col_name in pk_cols:
                note = "PK (composite)" if composite else "PK"
            else:
                note = ""
            lines.append(f"| `{col_name}` | {col_type} | {note} |")
        lines.append("")
        return lines

    with open(output_file_path, "w", encoding="utf-8") as f:
        def w(line: str = "") -> None:
            f.write(line + "\n")

        # ── Title & intro ────────────────────────────────────────────────────
        w("# Czech Parliament (PSP) Database Schema")
        w()
        w("Auto-generated by `etl_script.py` from [PSP open data](https://www.psp.cz/sqw/hp.sqw?k=1300).")
        w("See `erd.md` for an entity-relationship diagram.")
        w()

        # ── Table of contents ────────────────────────────────────────────────
        w("## Table of Contents")
        w()
        for group_name, tables in TABLE_GROUPS.items():
            w(f"- [{group_name}](#{_anchor(group_name)})")
            for t in tables:
                w(f"  - [{t}](#{t})")
            if group_name == "Voting":
                w(f"  - [hlasovani\\_\\<YEAR\\>s ({hl_first}–{hl_last})](#year-specific-voting-tables)")
        w(f"- [Year-specific voting tables](#year-specific-voting-tables)")
        w(f"- [Notes](#notes)")

        unclassified = [t for t in dynamic_schema if t not in grouped and t not in hl_year_set]
        if unclassified:
            w(f"- [Other Tables](#other-tables)")
        w()

        # ── Sections by group ────────────────────────────────────────────────
        for group_name, tables in TABLE_GROUPS.items():
            w(f"## {group_name}")
            w()
            for table_name in tables:
                for line in _table_section(table_name):
                    w(line)

        # ── Year-specific voting tables ──────────────────────────────────────
        w("## Year-specific voting tables")
        w()
        w(f"Tables `hlasovani_{hl_first}s` through `hlasovani_{hl_last}s` each hold one year's plenary vote sessions.")
        w("They share the same schema as [`hlasovani_session`](#hlasovani_session) and use `id_hlasovani` as their primary key.")
        w()
        w("| Table | Description |")
        w("|-------|-------------|")
        for y in _HL_YEARS:
            w(f"| `hlasovani_{y}s` | Plenary vote sessions for {y} |")
        w()

        # ── Notes ────────────────────────────────────────────────────────────
        w("## Notes")
        w()
        w("### `vysledek` vote result codes (hlasovani_poslanec)")
        w()
        w("| Code | Meaning |")
        w("|------|---------|")
        w("| `A`  | Ano — Yes |")
        w("| `B` / `N` | Ne — No |")
        w("| `C`  | Zdržel se — Abstain |")
        w("| `F`  | Nehlasoval (byl přihlášen) — Registered but did not press a button |")
        w("| `@`  | Nepřihlášen — Absent / not registered |")
        w("| `M`  | Omluven — Formally excused |")
        w("| `W`  | Před slibem — Before taking the oath (new MP) |")
        w("| `K`  | Zdržel / nehlasoval variant |")
        w()
        w("**Participation buckets used in `stat_mp`:**")
        w("- `present` = A B C F K (was registered, whether or not they pressed a button)")
        w("- `cast` = A B C (pressed a button with clear intent)")
        w("- `absent` = @ (not registered at all)")
        w("- `excused` = M")
        w()

        # ── Other (unclassified) tables ──────────────────────────────────────
        if unclassified:
            w("## Other Tables")
            w()
            w("_These tables appeared in the dynamic schema but are not assigned to a domain group above._")
            w()
            for table_name in sorted(unclassified):
                for line in _table_section(table_name):
                    w(line)

    logger.info("Markdown schema file generated.")


def compute_mp_stats(conn) -> None:
    """Compute and upsert per-MP summary statistics into the stat_mp table.

    Requires: osoba_poslanec, hlasovani_poslanec, tisk_tisky, tisk_predkladatel,
              tisk_navrh_podpis, steno_rec, interpelace_poradi tables to be populated.
    """
    logger.info("Computing stat_mp...")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stat_mp (
            id_poslanec           INTEGER PRIMARY KEY,
            id_osoba              INTEGER,
            term_id               INTEGER,
            votes_total           INTEGER,
            votes_present         INTEGER,
            votes_cast            INTEGER,
            votes_absent          INTEGER,
            votes_excused         INTEGER,
            participation_pct     REAL,
            bills_authored        INTEGER,
            bills_cosigned        INTEGER,
            bills_passed          INTEGER,
            bills_passed_pct      REAL,
            speeches_count        INTEGER,
            interpellations_count INTEGER,
            updated_at            TEXT DEFAULT (datetime('now'))
        );
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_hlasovani_omluvy_poslanec_organ_den
        ON hlasovani_omluvy(id_poslanec, id_organ, den);
    """)
    conn.commit()

    # voting stats — vysledek values:
    #   A=ano, B/N=ne, C=zdržel, F=nehlasoval (byl přihlášen), @=nepřihlášen,
    #   M=omluven, W=před slibem, K=zdržel/nehlasoval
    #   "present" = A B C F K (was registered, whether voted or not)
    #   "cast"    = A B C   (actually pressed a button with a clear intent)
    #   "absent"  = @  (not registered and no matching omluvy record)
    #   "excused" = M  (M in source data, OR @ reclassified via omluvy date+time match)
    #
    # omluvy reclassification: if vysledek='@' and the vote's date+time falls within
    # a filed excuse for that MP and organ, the vote is counted as excused (M), not absent.
    # Registered votes (A/B/N/C/F/K) always take precedence over any excuse on file.
    # Note: if PSP records excuses against the parent chamber organ while votes record
    # a sub-organ, the id_organ join will produce 0 matches — verify after first ETL run.
    union_sql = " UNION ALL ".join(
        f'SELECT id_hlasovani, id_organ, datum, "čas" AS cas FROM hlasovani_{y}s'
        for y in _HL_YEARS
    )
    cursor.execute(f"""
        WITH vote_sessions AS (
            {union_sql}
        )
        INSERT INTO stat_mp (
            id_poslanec, id_osoba, term_id,
            votes_total, votes_present, votes_cast, votes_absent, votes_excused,
            participation_pct,
            bills_authored, bills_cosigned, bills_passed, bills_passed_pct,
            speeches_count, interpellations_count,
            updated_at
        )
        SELECT
            p.id_poslanec,
            p.id_osoba,
            p.id_obdobi,
            COUNT(*)                                                        AS votes_total,
            SUM(CASE WHEN hp.vysledek IN ('A','B','N','C','F','K') THEN 1 ELSE 0 END) AS votes_present,
            SUM(CASE WHEN hp.vysledek IN ('A','B','N','C')         THEN 1 ELSE 0 END) AS votes_cast,
            SUM(CASE WHEN hp.vysledek = '@' AND om.den IS NULL
                THEN 1 ELSE 0 END)                                         AS votes_absent,
            SUM(CASE WHEN hp.vysledek = 'M'
                          OR (hp.vysledek = '@' AND om.den IS NOT NULL)
                THEN 1 ELSE 0 END)                                         AS votes_excused,
            ROUND(
                100.0 * SUM(CASE WHEN hp.vysledek IN ('A','B','N','C','F','K') THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                2
            )                                                               AS participation_pct,
            COALESCE(authored.cnt, 0)                                       AS bills_authored,
            COALESCE(cosigned.cnt, 0)                                       AS bills_cosigned,
            COALESCE(passed.cnt, 0)                                         AS bills_passed,
            ROUND(
                CASE WHEN COALESCE(authored.cnt, 0) > 0
                THEN 100.0 * COALESCE(passed.cnt, 0) / authored.cnt
                ELSE 0.0 END, 1
            )                                                               AS bills_passed_pct,
            COALESCE(speeches.cnt, 0)                                       AS speeches_count,
            COALESCE(interps.cnt, 0) + COALESCE(written_interps.cnt, 0)     AS interpellations_count,
            datetime('now')
        FROM osoba_poslanec p
        JOIN hlasovani_poslanec hp ON hp.id_poslanec = p.id_poslanec
        JOIN vote_sessions hh ON hh.id_hlasovani = hp.id_hlasovani
        LEFT JOIN hlasovani_omluvy om
            ON  om.id_poslanec = hp.id_poslanec
            AND om.id_organ    = hh.id_organ
            AND SUBSTR(hh.datum, 1, 10) = SUBSTR(om.den, 1, 10)
            AND (
                (om.od IS NULL AND om."do" IS NULL)
                OR (
                    (om.od  IS NULL OR SUBSTR(hh.cas, 1, 5) >= SUBSTR(om.od,    1, 5))
                AND (om."do" IS NULL OR SUBSTR(hh.cas, 1, 5) <= SUBSTR(om."do", 1, 5))
                )
            )
        LEFT JOIN (
            SELECT tp.id_osoba, t.id_org_obd, COUNT(*) AS cnt
            FROM tisk_predkladatel tp
            JOIN tisk_tisky t ON t.id_tisk = tp.id_tisk
            GROUP BY tp.id_osoba, t.id_org_obd
        ) authored  ON authored.id_osoba = p.id_osoba AND authored.id_org_obd = p.id_obdobi
        LEFT JOIN (
            SELECT np.id_osoba, t.id_org_obd, COUNT(*) AS cnt
            FROM tisk_navrh_podpis np
            JOIN tisk_tisky t ON t.id_tisk = np.id_tisk
            GROUP BY np.id_osoba, t.id_org_obd
        ) cosigned  ON cosigned.id_osoba = p.id_osoba AND cosigned.id_org_obd = p.id_obdobi
        LEFT JOIN (
            -- bills that became law: authored by MP and published in the law collection
            SELECT tp.id_osoba, t.id_org_obd, COUNT(DISTINCT tp.id_tisk) AS cnt
            FROM tisk_predkladatel tp
            JOIN tisk_tisky t ON t.id_tisk = tp.id_tisk
            JOIN tisk_sb_pre sbp ON sbp.id_tisk = tp.id_tisk
            GROUP BY tp.id_osoba, t.id_org_obd
        ) passed    ON passed.id_osoba = p.id_osoba AND passed.id_org_obd = p.id_obdobi
        LEFT JOIN (
            SELECT id_osoba, COUNT(*) AS cnt FROM steno_rec GROUP BY id_osoba
        ) speeches  ON speeches.id_osoba  = p.id_osoba
        LEFT JOIN (
            -- interpelace_los holds sessions; interpelace_poradi links MPs to oral interpellations (terms 165–167)
            SELECT id_poslanec, COUNT(*) AS cnt FROM interpelace_poradi GROUP BY id_poslanec
        ) interps   ON interps.id_poslanec = p.id_poslanec
        LEFT JOIN (
            -- písemné interpelace (written, id_druh=6) from tisk_tisky, terms 167+
            SELECT pw.id_poslanec, COUNT(*) AS cnt
            FROM tisk_tisky t
            JOIN osoba_poslanec pw ON pw.id_osoba = t.id_osoba AND pw.id_obdobi = t.id_org_obd
            WHERE t.id_druh = 6
            GROUP BY pw.id_poslanec
        ) written_interps ON written_interps.id_poslanec = p.id_poslanec
        GROUP BY p.id_poslanec
        ON CONFLICT (id_poslanec) DO UPDATE SET
            id_osoba              = excluded.id_osoba,
            term_id               = excluded.term_id,
            votes_total           = excluded.votes_total,
            votes_present         = excluded.votes_present,
            votes_cast            = excluded.votes_cast,
            votes_absent          = excluded.votes_absent,
            votes_excused         = excluded.votes_excused,
            participation_pct     = excluded.participation_pct,
            bills_authored        = excluded.bills_authored,
            bills_cosigned        = excluded.bills_cosigned,
            bills_passed          = excluded.bills_passed,
            bills_passed_pct      = excluded.bills_passed_pct,
            speeches_count        = excluded.speeches_count,
            interpellations_count = excluded.interpellations_count,
            updated_at            = excluded.updated_at;
    """)
    conn.commit()

    rows = cursor.execute("SELECT COUNT(*) FROM stat_mp;").fetchone()[0]
    logger.info(f"stat_mp: {rows} rows computed.")


def ensure_etl_tables(conn) -> None:
    """Create the ETL metadata tables if they don't exist yet."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etl_schema_cache (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etl_zip_state (
            zip_url        TEXT PRIMARY KEY,
            etag           TEXT,
            last_modified  TEXT,
            content_sha256 TEXT,
            processed_at   TEXT
        );
    """)
    conn.commit()


def load_schema_cache(conn) -> dict | None:
    """Load the cached schema dict from the DB, or None if absent/corrupt."""
    try:
        row = conn.execute(
            "SELECT value FROM etl_schema_cache WHERE key = 'schema';"
        ).fetchone()
        if not row:
            return None
        schema = json.loads(row[0])
        if not isinstance(schema, dict) or not schema:
            raise ValueError("empty or invalid")
        return schema
    except Exception as e:
        logger.warning(f"Schema cache unreadable ({e}), will re-fetch.")
        return None


def save_schema_cache(schema: dict, conn) -> None:
    """Upsert the schema dict into the DB for reuse across runs."""
    try:
        conn.execute(
            "INSERT INTO etl_schema_cache (key, value, updated_at) VALUES ('schema', ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;",
            (json.dumps(schema, ensure_ascii=False), datetime.datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        logger.info("Schema cache saved to DB (etl_schema_cache).")
    except Exception as e:
        logger.warning(f"Could not save schema cache: {e}")


def load_zip_state(conn) -> dict:
    """Load the ZIP state dict (etag/hash/processed_at per URL) from the DB."""
    try:
        rows = conn.execute(
            "SELECT zip_url, etag, last_modified, content_sha256, processed_at FROM etl_zip_state;"
        ).fetchall()
        return {
            row[0]: {
                "etag":           row[1],
                "last_modified":  row[2],
                "content_sha256": row[3],
                "processed_at":   row[4],
            }
            for row in rows
        }
    except Exception as e:
        logger.warning(f"ZIP state unreadable ({e}), treating all ZIPs as new.")
        return {}


def save_zip_state_entry(zip_url: str, entry: dict, conn) -> None:
    """Upsert a single ZIP state entry into the DB."""
    try:
        conn.execute(
            "INSERT INTO etl_zip_state (zip_url, etag, last_modified, content_sha256, processed_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (zip_url) DO UPDATE SET"
            "   etag           = excluded.etag,"
            "   last_modified  = excluded.last_modified,"
            "   content_sha256 = excluded.content_sha256,"
            "   processed_at   = excluded.processed_at;",
            (
                zip_url,
                entry.get("etag"),
                entry.get("last_modified"),
                entry.get("content_sha256"),
                entry.get("processed_at"),
            ),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Could not save ZIP state for {zip_url}: {e}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PSP Parliament ETL — load Czech parliament data.")
    parser.add_argument("--temp-dir", default=TEMP_DIR,
                        help="Directory for downloaded ZIPs and schema pages.")
    parser.add_argument("--db-url", default=DB_NAME,
                        help="Database URL: a libsql://... Turso URL or a local SQLite path. "
                             "Defaults to TURSO_DATABASE_URL → DATABASE_URL → local file.")
    parser.add_argument("--schema-file", default=SCHEMA_SQL_FILE,
                        help="Output SQL schema file path.")
    parser.add_argument("--schema-md-file", default=SCHEMA_MD_FILE,
                        help="Output Markdown schema file path.")
    parser.add_argument("--term", type=int, nargs="+", metavar="N",
                        help="Only load data for these electoral term numbers (e.g. --term 9 or --term 8 9). "
                             "Shared reference data (osoby, organy, etc.) is always included. "
                             "Run with --list-terms to see what is available.")
    parser.add_argument("--list-terms", action="store_true",
                        help="Print available terms and their ZIP counts, then exit.")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete extracted .unl files after loading each ZIP.")
    parser.add_argument("--skip-stats", action="store_true",
                        help="Skip the mp_stats computation step after loading.")
    parser.add_argument("--refresh-schema", action="store_true",
                        help="Re-download and re-parse schema HTML pages, replacing the local cache.")
    parser.add_argument("--force-download", action="store_true",
                        help="Re-download all ZIPs, ignoring cached hashes/ETags.")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        help="Logging verbosity (default: INFO).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    temp_dir = os.path.expanduser(args.temp_dir)
    extract_dir = os.path.join(temp_dir, "extracted_data")
    os.makedirs(extract_dir, exist_ok=True)

    logger.info("Starting ETL process.")

    all_zip_schema_pairs = get_zip_and_schema_urls(DATA_PAGE_URL)
    if not all_zip_schema_pairs:
        logger.critical(f"No ZIP entries found on {DATA_PAGE_URL}. Aborting.")
        return

    if args.list_terms:
        from collections import Counter
        counts = Counter(e["term"] for e in all_zip_schema_pairs)
        print("Available terms (term number → ZIP count):")
        for term in sorted(t for t in counts if t is not None):
            print(f"  {term:2d}. volební období — {counts[term]} ZIP(s)")
        unknown = counts.get(None, 0)
        if unknown:
            print(f"   ?  (shared / term not detected) — {unknown} ZIP(s)")
        return

    if args.term:
        requested = set(args.term)
        # Always include entries with no term (shared reference data: osoby, organy, etc.)
        all_zip_schema_pairs = [
            e for e in all_zip_schema_pairs
            if e["term"] in requested or e["term"] is None
        ]
        if not all_zip_schema_pairs:
            logger.critical(f"No ZIP entries found for term(s) {sorted(requested)}. "
                            f"Run with --list-terms to see what is available.")
            return
        logger.info(f"Filtered to term(s) {sorted(requested)}: {len(all_zip_schema_pairs)} ZIP(s) "
                     f"(including shared reference data).")

    total_zips = len(all_zip_schema_pairs)
    conn = None
    try:
        conn = connect_db(args.db_url, temp_dir)
        ensure_etl_tables(conn)

        dynamic_schema = None
        if not args.refresh_schema:
            dynamic_schema = load_schema_cache(conn)
            if dynamic_schema:
                logger.info("Using cached schema from DB. Pass --refresh-schema to re-fetch.")

        if dynamic_schema is None:
            dynamic_schema = get_all_schemas(all_zip_schema_pairs, temp_dir)
            if dynamic_schema:
                save_schema_cache(dynamic_schema, conn)

        if not dynamic_schema:
            logger.critical("No schema definitions found. Aborting.")
            return

        # Translate PSP source names to prefixed DB names (cache stores original PSP names).
        dynamic_schema = _rename_schema_keys(dynamic_schema)

        generate_sql_schema_file(dynamic_schema, PRIMARY_KEYS, args.schema_file)
        generate_md_schema_file(dynamic_schema, PRIMARY_KEYS, args.schema_md_file)

        create_all_tables(dynamic_schema, PRIMARY_KEYS, conn)

        zip_state = load_zip_state(conn)

        for zip_idx, entry in enumerate(all_zip_schema_pairs, 1):
            zip_url = entry["zip_url"]
            zip_name = os.path.splitext(os.path.basename(zip_url))[0]
            current_extract_dir = os.path.join(extract_dir, zip_name)
            os.makedirs(current_extract_dir, exist_ok=True)

            logger.info(f"[{zip_idx}/{total_zips}] Processing {zip_name}...")

            result_dir, data_was_new = download_and_extract_zip(
                zip_url, current_extract_dir, zip_state, force=args.force_download
            )
            if result_dir is None:
                logger.warning(f"[{zip_idx}/{total_zips}] Skipping {zip_url} due to download/extraction error.")
                continue

            if data_was_new:
                for unl_file in (f for f in os.listdir(current_extract_dir) if f.endswith('.unl')):
                    file_base = os.path.splitext(unl_file)[0].lower()
                    target_table = _resolve_table(file_base)
                    # Schema lookup: use the resolved target (which is the base table name)
                    schema_key = target_table
                    if schema_key not in dynamic_schema:
                        logger.warning(f"No schema for '{unl_file}' (resolved to '{target_table}'). Skipping.")
                        continue
                    df = parse_unl_file(os.path.join(current_extract_dir, unl_file), dynamic_schema[schema_key])
                    load_to_db(df, target_table, PRIMARY_KEYS, conn)

                # Mark as processed BEFORE cleanup so --cleanup + next run still skips
                zip_state[zip_url] = {
                    **zip_state.get(zip_url, {}),
                    "processed_at": datetime.datetime.now().isoformat(timespec="seconds"),
                }

            # Always persist the entry if it exists (covers new downloads, header drift,
            # and processed_at being set above — all in one upsert)
            if zip_url in zip_state:
                save_zip_state_entry(zip_url, zip_state[zip_url], conn)

            if args.cleanup:
                shutil.rmtree(current_extract_dir, ignore_errors=True)
                logger.info(f"  Cleaned up {current_extract_dir}")

        if not args.skip_stats:
            compute_mp_stats(conn)

        if args.db_url.startswith("libsql://"):
            import time as _time
            logger.info("Syncing local replica to Turso (this uploads all data — may take minutes)...")
            t_sync = _time.monotonic()
            conn.sync()
            logger.info(f"Sync complete in {_time.monotonic() - t_sync:.1f}s")

    except Exception as e:
        logger.critical(f"Database error: {e}. Aborting.")
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

    logger.info(f"ETL complete. Database: {args.db_url}")


if __name__ == "__main__":
    main()
