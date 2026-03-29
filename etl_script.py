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
    "hl_hlasovani": [f"hl{y}s" for y in _HL_YEARS],
}

# Year-specific file variants (e.g. hl2021h1) should be consolidated into
# their base table instead of creating one table per year × suffix.
_HL_FILE_REDIRECT: list[tuple[re.Pattern, str]] = [
    (re.compile(r'^hl\d{4}h\d$'), 'hl_poslanec'),
    (re.compile(r'^hl\d{4}v$'),   'hl_vazby'),
    (re.compile(r'^hl\d{4}x$'),   'hl_zposlanec'),
    (re.compile(r'^hl\d{4}z$'),   'hl_check'),
]


def _resolve_table(name: str) -> str:
    """Map a filename-derived table name to its consolidation target, if any."""
    for pattern, target in _HL_FILE_REDIRECT:
        if pattern.match(name):
            return target
    return name

PRIMARY_KEYS = {
    "osoby":          ["id_osoba"],
    "funkce":         ["id_funkce"],
    "organy":         ["id_organ"],
    "typ_funkce":     ["id_typ_funkce"],
    "typ_organu":     ["id_typ_org"],
    "zarazeni":       ["id_osoba", "id_of", "od_o"],
    "poslanec":       ["id_poslanec"],
    "pkgps":          ["id_poslanec"],
    "osoba_extra":    ["id_osoba", "id_org", "typ"],
    "hl_hlasovani":   ["id_hlasovani"],
    "zmatecne":       ["id_hlasovani"],
    "omluvy":         ["id_organ", "id_poslanec", "den"],  # od (time) can be NULL — excluded from PK
    "hl_poslanec":    ["id_poslanec", "id_hlasovani"],
    "hl_check":       ["id_hlasovani", "turn"],   # cols: id_hlasovani, turn, mode, id_h2, id_h3
    "hl_zposlanec":   ["id_hlasovani", "id_osoba"], # cols: id_hlasovani, id_osoba, mode
    "hl_vazby":       ["id_hlasovani", "turn"],     # cols: id_hlasovani, turn, typ
    "druh_tisku":     ["id_druh"],
    "typ_zakon":      ["id_navrh"],
    "typ_stavu":      ["id_typ"],
    "stavy":          ["id_stav"],
    "typ_akce":       ["id_akce"],
    "prechody":       ["id_prechod"],
    "tisky":          ["id_tisk"],
    "tz_eklep":       ["id_tisk", "cislo_za"],
    "hist":           ["id_hist"],
    "tisky_za":       ["id_tisk", "cislo_za"],
    "vysledek":       ["id_vysledek"],
    "tisk_eklep":     ["id_tisk", "cislo_za"],
    "hist_vybory":    ["id_hist"],
    "predkladatel":   ["id_tisk", "id_osoba"],
    "navrh_podpis":   ["id_tisk", "id_osoba"],
    "schuze":         ["id_schuze"],
    "bod_schuze":     ["id_schuze", "id_bod"],
    "bod_stav":       ["id_bod_stav"],
    "schuze_stav":    ["id_schuze", "stav"],
    "uitypv":         ["id_ui_stav"],
    "los_interpelaci":["id_los"],
    "poradi":         ["id_poradi"],
    "ui_stav":        ["id_poradi", "id_typ"],
    "sd_dokument":    ["id_dokument"],
    "druh_predpisu":  ["id_dp"],
    "sbirka":         ["id_sbirka"],
    "sb_pre":         ["id_tisk", "id_sbirka"],
    "steno":          ["id_steno"],
    "steno_bod":      ["id_steno", "aname"],
    "rec":            ["id_steno", "aname"],
    "se_tisk":        ["id_tisk"],
    "psp2senat":      ["id_psp", "id_senat"],
    "se_druh_tisku":  ["id_druh"],
}
# Year-specific session tables (hl2021s, hl2022s, …) share the hl_hlasovani PK.
# They are kept as separate tables for per-year queries rather than consolidated.
for _y in _HL_YEARS:
    PRIMARY_KEYS[f"hl{_y}s"] = ["id_hlasovani"]


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


def compute_mp_stats(conn) -> None:
    """Compute and upsert per-MP summary statistics into the mp_stats table.

    Requires: poslanec, hl_poslanec, tisky, predkladatel, navrh_podpis,
              rec, los_interpelaci tables to be populated.
    """
    logger.info("Computing mp_stats...")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mp_stats (
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
            speeches_count        INTEGER,
            interpellations_count INTEGER,
            updated_at            TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # voting stats — vysledek values:
    #   A=ano, B/N=ne, C=zdržel, F=nehlasoval (byl přihlášen), @=nepřihlášen,
    #   M=omluven, W=před slibem, K=zdržel/nehlasoval
    #   "present" = A B C F K (was registered, whether voted or not)
    #   "cast"    = A B C   (actually pressed a button with a clear intent)
    #   "absent"  = @        (not registered at all)
    #   "excused" = M
    cursor.execute("""
        INSERT INTO mp_stats (
            id_poslanec, id_osoba, term_id,
            votes_total, votes_present, votes_cast, votes_absent, votes_excused,
            participation_pct,
            bills_authored, bills_cosigned,
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
            SUM(CASE WHEN hp.vysledek = '@'                        THEN 1 ELSE 0 END) AS votes_absent,
            SUM(CASE WHEN hp.vysledek = 'M'                        THEN 1 ELSE 0 END) AS votes_excused,
            ROUND(
                100.0 * SUM(CASE WHEN hp.vysledek IN ('A','B','N','C','F','K') THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0),
                2
            )                                                               AS participation_pct,
            COALESCE(authored.cnt, 0)                                       AS bills_authored,
            COALESCE(cosigned.cnt, 0)                                       AS bills_cosigned,
            COALESCE(speeches.cnt, 0)                                       AS speeches_count,
            COALESCE(interps.cnt, 0)                                        AS interpellations_count,
            datetime('now')
        FROM poslanec p
        JOIN hl_poslanec hp ON hp.id_poslanec = p.id_poslanec
        LEFT JOIN (
            SELECT id_osoba, COUNT(*) AS cnt FROM predkladatel GROUP BY id_osoba
        ) authored  ON authored.id_osoba  = p.id_osoba
        LEFT JOIN (
            SELECT id_osoba, COUNT(*) AS cnt FROM navrh_podpis GROUP BY id_osoba
        ) cosigned  ON cosigned.id_osoba  = p.id_osoba
        LEFT JOIN (
            SELECT id_osoba, COUNT(*) AS cnt FROM rec GROUP BY id_osoba
        ) speeches  ON speeches.id_osoba  = p.id_osoba
        LEFT JOIN (
            -- los_interpelaci holds sessions; poradi links MPs to interpellations
            SELECT id_poslanec, COUNT(*) AS cnt FROM poradi GROUP BY id_poslanec
        ) interps   ON interps.id_poslanec = p.id_poslanec
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
            speeches_count        = excluded.speeches_count,
            interpellations_count = excluded.interpellations_count,
            updated_at            = excluded.updated_at;
    """)
    conn.commit()

    rows = cursor.execute("SELECT COUNT(*) FROM mp_stats;").fetchone()[0]
    logger.info(f"mp_stats: {rows} rows computed.")


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

        generate_sql_schema_file(dynamic_schema, PRIMARY_KEYS, args.schema_file)

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
