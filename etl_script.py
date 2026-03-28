import pandas as pd
import requests
from bs4 import BeautifulSoup
import zipfile
import os
import sqlite3
from io import BytesIO
import urllib.parse
import logging
import numpy as np # Import numpy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the base URL for the data
BASE_URL = "https://www.psp.cz"
DATA_PAGE_URL = f"{BASE_URL}/sqw/hp.sqw?k=1300"
# TEMP_DIR for downloads and extracted files
TEMP_DIR = "/Users/jan.paces/.gemini/tmp/5e0ab42036398c20af3f5e62aad2dab5fb6a264ff1458dea64d3601da2d35661"
EXTRACT_DIR = os.path.join(TEMP_DIR, "extracted_data")
DB_NAME = os.path.join(TEMP_DIR, "parliament_data.db")
SCHEMA_SQL_FILE = "schema.sql"

# Inferred Primary Keys for each table
PRIMARY_KEYS = {
    "osoby": ["id_osoba"],
    "funkce": ["id_funkce"],
    "organy": ["id_organ"],
    "typ_funkce": ["id_typ_funkce"],
    "typ_organu": ["id_typ_org"],
    "zarazeni": ["id_osoba", "id_of", "od_o"], # Composite key
    "poslanec": ["id_poslanec"],
    "pkgps": ["id_poslanec"],
    "osoba_extra": ["id_osoba", "id_org", "typ"], # Composite key, or id_external could be PK
    # Voting-related tables
    "hl_hlasovani": ["id_hlasovani"], # Generic for hlYYYY files
    "zmatecne": ["id_hlasovani"],
    "omluvy": [], # Removed id_hlasovani as it's not present in the table schema
    "hl_poslanec": ["id_poslanec", "id_hlasovani"], # Assuming composite
    "hl_check": ["id_hlasovani"],
    "hl_zposlanec": ["id_poslanec", "id_hlasovani"],
    "hl_vazby": ["id_hlasovani", "id_organ"], # Assuming composite
    # tisky (parliamentary prints)
    "druh_tisku": ["id_druh_tisku"],
    "typ_zakon": ["id_typ_zakon"],
    "typ_stavu": ["id_typ_stavu"],
    "stavy": ["id_stav"],
    "typ_akce": ["id_typ_akce"],
    "prechody": ["id_prechod"],
    "tisky": ["id_tisk"],
    "tz_eklep": ["id_tz_eklep"],
    "hist": ["id_hist"],
    "tisky_za": ["id_tisk", "id_osoba"], # Composite
    "vysledek": ["id_vysledek"],
    "tisk_eklep": ["id_tisk_eklep"],
    "hist_vybory": ["id_hist_vybory"],
    "predkladatel": ["id_predkladatel"],
    "navrh_podpis": ["id_navrh_podpis"],
    "schuze": ["id_schuze"],
    "bod_schuze": ["id_schuze", "id_bod"], # Composite
    "bod_stav": ["id_bod", "id_stav"], # Composite
    "schuze_stav": ["id_schuze", "id_stav"], # Composite
    "uitypv": ["id_interpelace", "id_poslanec"], # Assuming composite
    "los_interpelaci": ["id_interpelace"],
    "poradi": ["id_poradi"],
    "ui_stav": ["id_ui_stav"],
    "sd_dokument": ["id_dokument"],
    "druh_predpisu": ["id_druh_predpisu"],
    "sbirka": ["id_sbirka"],
    "sb_pre": ["id_sbirka", "id_predpis"], # Composite
    "steno": ["id_steno"],
    "steno_bod": ["id_steno_bod"],
    "rec": ["id_rec"],
    "se_tisk": ["id_se_tisk"],
    "psp2senat": ["id_psp", "id_senat"], # Composite
    "se_druh_tisku": ["id_se_druh_tisku"],
}

def extract_schema_from_html(html_file_path):
    """
    Extracts schema definitions for UNL files from the HTML documentation page.
    """
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
        if h2_tag.text.strip().startswith('Tabulka '):
            table_name_cz = h2_tag.text.strip().replace('Tabulka ', '')
            unl_file_key = table_name_cz.lower()
            
            table_tag = h2_tag.find_next_sibling('table')
            if table_tag:
                current_table_schema = []
                # Get all rows in the table
                all_trs = table_tag.find_all('tr')
                # Assume the first row is the header if it contains 'Sloupec' in the first td
                start_row_index = 0
                if all_trs and all_trs[0].find('td') and 'Sloupec' in all_trs[0].find('td').text:
                    start_row_index = 1 # Skip the first row (header)

                for tr in all_trs[start_row_index:]:
                    cols = tr.find_all('td')
                    if len(cols) >= 2:
                        column_name = cols[0].text.strip()
                        column_type = cols[1].text.strip()
                        current_table_schema.append({"name": column_name, "type": column_type})
                if current_table_schema:
                    dynamic_schema[unl_file_key] = current_table_schema

                    # Special handling for voting tables (hl_hlasovani)
                    # Map the 'hl_hlasovani' schema to specific UNL file names.
                    if unl_file_key == "hl_hlasovani":
                        for year in range(1993, 2026): # Covers years from 1993 to 2025
                            dynamic_schema[f"hl{year}s"] = current_table_schema
                            dynamic_schema[f"hl{year}h1"] = current_table_schema
                            dynamic_schema[f"hl{year}h2"] = current_table_schema
                            dynamic_schema[f"hl{year}h3"] = current_table_schema # Some years might have h3
                            dynamic_schema[f"hl{year}v"] = current_table_schema
                            dynamic_schema[f"hl{year}x"] = current_table_schema
                            dynamic_schema[f"hl{year}z"] = current_table_schema
                    
                    # Special handling for 'tisky' (parliamentary prints)
                    if unl_file_key == "tisky":
                        dynamic_schema["tz_eklep"] = current_table_schema
                        dynamic_schema["typ_stavu"] = current_table_schema
                        dynamic_schema["hist"] = current_table_schema
                        dynamic_schema["typ_akce"] = current_table_schema
                        dynamic_schema["tisky_za"] = current_table_schema
                        dynamic_schema["prechody"] = current_table_schema
                        dynamic_schema["druh_tisku"] = current_table_schema
                        dynamic_schema["typ_zakon"] = current_table_schema
                        dynamic_schema["vysledek"] = current_table_schema
                        dynamic_schema["tisk_eklep"] = current_table_schema
                        dynamic_schema["stavy"] = current_table_schema
                        dynamic_schema["hist_vybory"] = current_table_schema
                        dynamic_schema["predkladatel"] = current_table_schema
                    
                    # Special handling for 'interp' (oral interpellations)
                    if unl_file_key == "interp":
                        dynamic_schema["p-stav"] = current_table_schema
                        dynamic_schema["uitypv"] = current_table_schema
                        dynamic_schema["li"] = current_table_schema
                        dynamic_schema["poradi"] = current_table_schema
                    
                    # Special handling for 'steno' (stenographic records)
                    if unl_file_key == "steno":
                        dynamic_schema["steno_bod"] = current_table_schema
                        dynamic_schema["rec"] = current_table_schema
                    
                    # Special handling for 'sd' (parliamentary documents)
                    if unl_file_key == "sd":
                        dynamic_schema["sd_dokument"] = current_table_schema
                    
                    # Special handling for 'sbirka' (collection of laws)
                    if unl_file_key == "sbirka":
                        dynamic_schema["druh_predpisu"] = current_table_schema
                        dynamic_schema["sb_pre"] = current_table_schema
                    
                    # Special handling for 'schuze' (sessions)
                    if unl_file_key == "schuze":
                        dynamic_schema["bod_schuze"] = current_table_schema
                        dynamic_schema["bod_stav"] = current_table_schema
                        dynamic_schema["schuze_stav"] = current_table_schema

                    # Special handling for 'se_tisk' (senate prints)
                    if unl_file_key == "se_tisk":
                        dynamic_schema["psp2senat"] = current_table_schema
                        dynamic_schema["se_druh_tisku"] = current_table_schema


    logger.info(f"Schema extraction completed for {html_file_path}.")
    return dynamic_schema

def download_and_extract_zip(zip_url, extract_to_dir):
    logger.info(f"Downloading {zip_url}...")
    try:
        response = requests.get(zip_url, stream=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download {zip_url}: {e}")
        return None

    try:
        with zipfile.ZipFile(BytesIO(response.content)) as zip_ref:
            zip_ref.extractall(extract_to_dir)
        logger.info(f"Extracted {zip_url} to {extract_to_dir}")
        return extract_to_dir
    except zipfile.BadZipFile:
        logger.error(f"Downloaded file is not a valid ZIP file: {zip_url}")
        return None
    except Exception as e:
        logger.error(f"Error extracting ZIP file {zip_url}: {e}")
        return None

def parse_unl_file(file_path, schema_def):
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
            na_values=['']
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
    
    # Apply type conversions
    for col_def in schema_def:
        col_name = col_def["name"]
        col_type = col_def["type"]

        if col_name in df.columns:
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
                logger.warning(f"Failed to convert column '{col_name}' to type '{col_type}' in file '{file_path}': {e}. Column will remain as object/string.")
    
    return df

def create_table_with_pk(table_name, schema_def, primary_keys, conn):
    """
    Creates an SQLite table with explicit primary key constraints.
    """
    columns_sql = []
    for col in schema_def:
        col_name = col["name"]
        col_type = col["type"]
        sqlite_type = "TEXT" # Default
        if "int" in col_type:
            sqlite_type = "INTEGER"
        elif "date" in col_type or "datetime" in col_type:
            sqlite_type = "TEXT" # Store as ISO-formatted string
        
        columns_sql.append(f"{col_name} {sqlite_type}")
    
    pk_constraint = ""
    if table_name in primary_keys and primary_keys[table_name]:
        pk_cols = ", ".join(primary_keys[table_name])
        pk_constraint = f", PRIMARY KEY ({pk_cols})"
    
    create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns_sql)}{pk_constraint});"
    
    try:
        conn.execute(create_table_sql)
        conn.commit()
        logger.info(f"Table '{table_name}' created or already exists with primary key(s): {primary_keys.get(table_name)}")
    except sqlite3.Error as e:
        logger.error(f"Error creating table '{table_name}': {e}")

def load_to_sqlite(df, table_name, schema_def, primary_keys, conn, chunk_size=10000):
    logger.info(f"Loading data to table: {table_name}")
    if df.empty:
        logger.warning(f"DataFrame for {table_name} is empty. Skipping load.")
        return
    
    # Replace pd.NaT and np.nan with None for sqlite3 compatibility
    df = df.replace({pd.NaT: None, np.nan: None})

    # Convert datetime.time objects and Timestamp objects to strings for sqlite3 compatibility
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # Convert pandas Timestamps to ISO format strings
            df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S').fillna(value=np.nan).replace({np.nan: None})
        elif df[col].dtype == 'object': # This might contain Python datetime.time objects
            # Use apply to avoid SettingWithCopyWarning and handle element-wise
            df[col] = df[col].apply(lambda x: str(x) if isinstance(x, type(pd.to_datetime('00:00', format='%H:%M').time())) else x)
        # Ensure any remaining pandas Timestamp (if not caught by is_datetime64_any_dtype) are handled
        df[col] = df[col].apply(lambda x: None if pd.isna(x) else (x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, pd.Timestamp) else x))


    # Ensure table exists with primary key
    create_table_with_pk(table_name, schema_def, primary_keys, conn)

    # Prepare for INSERT OR REPLACE
    columns = ", ".join(df.columns)
    placeholders = ", ".join(["?" for _ in df.columns])
    
    # If primary keys are defined, use INSERT OR REPLACE
    if table_name in primary_keys and primary_keys[table_name]:
        insert_sql = f"INSERT OR REPLACE INTO {table_name} ({columns}) VALUES ({placeholders});"
    else:
        # If no explicit PK, just append. User will need to handle duplicates manually if needed.
        # This is a fallback and might not be ideal for incremental updates without a PK.
        insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders});"
        logger.warning(f"No explicit primary key defined for table '{table_name}'. Using INSERT (potential for duplicates).")

    try:
        cursor = conn.cursor()
        # Process DataFrame in chunks
        for i in range(0, len(df), chunk_size):
            chunk_df = df.iloc[i:i + chunk_size]
            data_to_insert = [tuple(row) for row in chunk_df.values]
            cursor.executemany(insert_sql, data_to_insert)
            conn.commit() # Commit after each chunk
            logger.info(f"Loaded {len(chunk_df)} rows for {table_name} (chunk {i // chunk_size + 1}).")
        
        logger.info(f"Data loaded (or replaced) for {table_name}: {len(df)} total rows.")
    except sqlite3.Error as e:
        logger.error(f"Error loading data to table {table_name}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading data to {table_name}: {e}")

def get_zip_and_schema_urls(data_page_url):
    """
    Fetches the data page and extracts all relevant ZIP file URLs and their associated schema documentation URLs.
    Returns a list of dictionaries: [{"zip_url": "...", "schema_doc_url": "..."}, ...]
    """
    logger.info(f"Fetching data page to discover ZIP files and schema URLs from {data_page_url}...")
    zip_schema_pairs = []
    try:
        response = requests.get(data_page_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the main data table
        # Assuming the data is within the first <table> after the "Data Poslanecké sněmovny a Senátu" heading
        data_table = soup.find('table', border="1") # Or more specific selector if needed

        if data_table:
            # Iterate through table rows
            for tr in data_table.find_all('tr', valign='top'):
                zip_url = None
                schema_doc_url = None

                # Find the ZIP file link
                zip_link_tag = tr.find('a', href=lambda href: href and href.endswith('.zip'))
                if zip_link_tag:
                    zip_url = urllib.parse.urljoin(BASE_URL, zip_link_tag['href'])
                
                # Find the schema documentation link (typically in the second <td> of the row)
                # It's an <a> tag where href starts with "hp.sqw?k="
                schema_link_tag = tr.find('a', href=lambda href: href and href.startswith('hp.sqw?k='))
                if schema_link_tag:
                    schema_doc_url = urllib.parse.urljoin(data_page_url, schema_link_tag['href'])
                
                if zip_url: # Only add if we found a ZIP URL
                    zip_schema_pairs.append({
                        "zip_url": zip_url,
                        "schema_doc_url": schema_doc_url # Can be None if no specific schema doc found for this ZIP
                    })
        else:
            logger.warning(f"Could not find the main data table on {data_page_url}.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch data page {data_page_url}: {e}")
    except Exception as e:
        logger.error(f"Error parsing data page HTML {data_page_url}: {e}")
    
    logger.info(f"Discovered {len(zip_schema_pairs)} ZIP file entries.")
    return zip_schema_pairs

def get_all_schemas(zip_schema_pairs):
    """
    Downloads and extracts schemas from all unique schema documentation URLs.
    Returns a single aggregated schema dictionary.
    """
    logger.info("Aggregating schema definitions from all discovered documentation pages.")
    aggregated_schema = {}
    unique_schema_urls = set()

    for entry in zip_schema_pairs:
        if entry["schema_doc_url"]:
            unique_schema_urls.add(entry["schema_doc_url"])
    
    for schema_doc_url in unique_schema_urls:
        # Create a unique filename for the schema HTML page
        schema_page_basename = os.path.basename(urllib.parse.urlparse(schema_doc_url).path)
        # Add the query string as well to differentiate pages like hp.sqw?k=1301 and hp.sqw?k=1302
        query_string = urllib.parse.urlparse(schema_doc_url).query
        schema_html_filename = f"{schema_page_basename}_{query_string}.html" if query_string else f"{schema_page_basename}.html"
        
        schema_html_path = os.path.join(TEMP_DIR, schema_html_filename)

        if not os.path.exists(schema_html_path):
            logger.info(f"Downloading schema documentation page to {schema_html_path}...")
            try:
                response = requests.get(schema_doc_url)
                response.raise_for_status()
                with open(schema_html_path, 'wb') as f:
                    f.write(response.content)
                logger.info("Schema documentation downloaded.")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download schema documentation from {schema_doc_url}: {e}. Skipping schema extraction for this page.")
                continue
        
        extracted_schema = extract_schema_from_html(schema_html_path)
        aggregated_schema.update(extracted_schema) # Merge schemas

    logger.info(f"Aggregated schema contains definitions for {len(aggregated_schema)} tables.")
    return aggregated_schema

def generate_sql_schema_file(dynamic_schema, primary_keys, output_file_path):
    """
    Generates a SQL schema file from the dynamic schema definitions.
    """
    logger.info(f"Generating SQL schema file: {output_file_path}")
    with open(output_file_path, 'w', encoding='utf-8') as f:
        for table_name, schema_def in dynamic_schema.items():
            columns_sql = []
            for col in schema_def:
                col_name = col["name"]
                col_type = col["type"]
                sqlite_type = "TEXT" # Default
                if "int" in col_type:
                    sqlite_type = "INTEGER"
                elif "date" in col_type or "datetime" in col_type:
                    sqlite_type = "TEXT" # Store as ISO-formatted string
                
                columns_sql.append(f"{col_name} {sqlite_type}")
            
            pk_constraint = ""
            if table_name in primary_keys and primary_keys[table_name]:
                pk_cols = ", ".join(primary_keys[table_name])
                pk_constraint = f", PRIMARY KEY ({pk_cols})"
            
            create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns_sql)}{pk_constraint});\n"
            f.write(create_table_sql)
    logger.info("SQL schema file generated successfully.")

def main():
    logger.info("Starting ETL process.")
    if not os.path.exists(EXTRACT_DIR):
        os.makedirs(EXTRACT_DIR)
        logger.info(f"Created extraction directory: {EXTRACT_DIR}")

    # 1. Discover all ZIP file URLs and their associated schema documentation URLs
    all_zip_schema_pairs = get_zip_and_schema_urls(DATA_PAGE_URL)
    if not all_zip_schema_pairs:
        logger.critical(f"No ZIP file entries found on {DATA_PAGE_URL}. Aborting ETL.")
        return

    # 2. Aggregate all schema definitions from the discovered documentation pages
    dynamic_schema = get_all_schemas(all_zip_schema_pairs)
    
    if not dynamic_schema:
        logger.critical("Failed to aggregate any schema definitions. Aborting ETL.")
        return

    # Generate SQL schema file
    generate_sql_schema_file(dynamic_schema, PRIMARY_KEYS, SCHEMA_SQL_FILE)

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        logger.info(f"Connected to SQLite database: {DB_NAME}")

        # 3. Process each discovered ZIP file
        for entry in all_zip_schema_pairs:
            zip_file_url = entry["zip_url"]
            zip_file_name_base = os.path.splitext(os.path.basename(zip_file_url))[0]
            current_extract_dir = os.path.join(EXTRACT_DIR, zip_file_name_base)
            
            if not os.path.exists(current_extract_dir):
                os.makedirs(current_extract_dir)
                logger.info(f"Created extraction directory for {zip_file_name_base}: {current_extract_dir}")

            extracted_data_path = download_and_extract_zip(zip_file_url, current_extract_dir)
            
            if extracted_data_path:
                # Process each UNL file in the extracted directory
                unl_files_in_zip = [f for f in os.listdir(current_extract_dir) if f.endswith('.unl')]

                for unl_file_name in unl_files_in_zip:
                    table_name = os.path.splitext(unl_file_name)[0].lower()
                    if table_name in dynamic_schema:
                        unl_file_path = os.path.join(current_extract_dir, unl_file_name)
                        df = parse_unl_file(unl_file_path, dynamic_schema[table_name])
                        # Pass primary_keys to load_to_sqlite
                        load_to_sqlite(df, table_name, dynamic_schema[table_name], PRIMARY_KEYS, conn)
                    else:
                        logger.warning(f"No schema found for UNL file '{unl_file_name}'. Skipping.")
            else:
                logger.warning(f"Skipping processing for {zip_file_url} due to previous download/extraction error.")


    except sqlite3.Error as e:
        logger.critical(f"Database error: {e}. Aborting ETL.")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred: {e}. Aborting ETL.")
    finally:
        if conn:
            conn.close()
            logger.info("Disconnected from SQLite database.")
            
    logger.info(f"ETL process completed. Database saved to: {DB_NAME}")

if __name__ == "__main__":
    main()