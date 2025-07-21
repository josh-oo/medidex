import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import os

import subprocess
import pandas as pd
import io
import ftfy

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")

def access_to_sql(file_path):

    # Step 1: Get list of tables
    tables_raw = subprocess.check_output(["mdb-tables", "-1", file_path])
    tables = tables_raw.decode("utf-8").strip().split('\n')
    print(f"Found {len(tables)} tables:\n", tables)

    # Step 2: Open SQLite DB
    conn = sqlite3.connect("from_mdb.sqlite")

    mojibake_mapping = {
        b"\xc3\xa2\xc3\xa2?\xc2\xac\xc3\xa2?\xc2\xa2":  b"'",
        b"\xc3\xa2\xc3\xa2?\xc2\xac\xc3\xa2??":         b"-",
        b"\xef\x82\x81\xef\x81\xbd":                    b"&plusmn;",
        b"\xef\x80\xab\xef\x80\xad":                    b"&plusmn;",
        b"\xc3\xa2?\xc3\x82\xc2\xa5":                   b">=",
        #b"\xe2\x82\xac\xc2\x90":                       b"\xe2\x82\xac\xc2\x90", #skip (only dupstring)
        b"\xc3\xa2\xe2\x82\xac":                        b"'",
        b"\xc3\xa2?\xc2\xa4":                           b"<=",
        b"\xef\xa0\x95":                                b"",
    }

    def decode_blob_like_text(val):
        if isinstance(val, bytes):
            try:
                return val.decode('utf-8', errors='replace')
            except:
                return str(val)  # fallback to str
        if isinstance(val, str):
            # Remove non-printable/control characters
            return ''.join(ch for ch in val if ch.isprintable())
        return val

    # Step 3: Export each table using mdb-export and import into SQLite
    for table in tables:
        print(f"\n⏳ Exporting table: {table}")
        try:
            cmds =[
                "mdb-export",
                "--datetime-format", "%Y-%m-%d %H:%M:%S",
            ]
            cmds += [file_path, table]
            csv_bytes = subprocess.check_output(cmds)

            all_mojibakes = []

            def decode_line(line_bytes):
                tmp_text = ftfy.fix_encoding(line_bytes.decode("utf-8"))
                line_bytes = tmp_text.encode("utf-8")
                for old, new in mojibake_mapping.items():
                    if old in line_bytes:
                        line_bytes = line_bytes.replace(old, new)
                return line_bytes.decode("utf-8", errors="replace")

            decoded_lines = [
                decode_line(line) for line in io.BytesIO(csv_bytes).readlines()
            ]

            csv_data = ''.join(decoded_lines)

            df = pd.read_csv(io.StringIO(csv_data), low_memory=False)

            if table == "tblReport":
                df['Abstract'] = df['Abstract'].apply(decode_blob_like_text)
                df['Title'] = df['Title'].apply(decode_blob_like_text)

            # Save to SQLite
            df.to_sql(table, conn, if_exists='replace', index=False)
            print(f"✅ Imported table: {table} ({len(df)} rows)")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to export/import table {table}: {e}")

    # Done
    conn.close()
    print("\n🎉 All tables exported from MDB and saved to SQLite!")

def normalize_date_time(tbl_name, column_name, id_column):

    # Connect to your SQLite database
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME,"meerkat.db"))
    cursor = conn.cursor()

    def format_to_iso(date_str):
        # Parse the date using datetime.strptime
        dt = datetime.strptime(date_str, "%m/%d/%y %H:%M:%S")
        
        # Return the formatted date in ISO 8601 format (YYYY-MM-DD)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Fetch data from the table
    cursor.execute(f"SELECT {id_column}, {column_name} FROM {tbl_name}")  # Replace with your actual table and column names
    rows = cursor.fetchall()

    # Loop over the fetched rows, apply the format_date function, and update the table
    for row in rows:
        row_id = row[0]
        date_column = row[1]

        # Skip rows where date_column is None or empty
        if not date_column:
            continue

        try:
            formatted_date = format_to_iso(date_column)
            cursor.execute(
                f"UPDATE {tbl_name} SET {column_name} = ? WHERE {id_column} = ?",
                (formatted_date, row_id),
            )
        except Exception as e:
            print(f"Skipping row {row_id}: invalid date format: {date_column} ({e})")


    # Commit the changes and close the connection
    conn.commit()
    conn.close()
    print(f"Normalized: {tbl_name} - {column_name}")

def remove_non_informative_values():
    #tblReport Abstract:
    #No abstract available
    #No Results Available
    #tblReport Title:
    #Personal Communication
    pass

def rename_columns():
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME,"meerkat.db"))
    cursor = conn.cursor()
    cursor.execute(f"ALTER TABLE tblStudy RENAME COLUMN UDef1 TO NumberParticipants;")
    cursor.execute(f"ALTER TABLE tblStudy RENAME COLUMN UDef2 TO Countries;")
    cursor.execute(f"ALTER TABLE tblStudy RENAME COLUMN UDef3 TO Duration;")
    cursor.execute(f"ALTER TABLE tblStudy RENAME COLUMN UDef5 TO Comparison;")
    cursor.execute(f"ALTER TABLE tblStudy RENAME COLUMN UDef7 TO TrialRegistrationID;")

    cursor.execute(f"ALTER TABLE tblReport RENAME COLUMN UDef1 TO StudyDesign;")
    cursor.execute(f"ALTER TABLE tblReport RENAME COLUMN UDef2 TO DOI;")
    cursor.execute(f"ALTER TABLE tblReport RENAME COLUMN UDef4 TO ISBN;")
    cursor.execute(f"ALTER TABLE tblReport RENAME COLUMN UDef6 TO PMID;")
    cursor.execute(f"ALTER TABLE tblReport RENAME COLUMN UDef7 TO TrialRegistrationID;")
    conn.commit()
    conn.close()
    

#access_to_sql("")
rename_columns()
#normalize_date_time("tblStudy", "DateEntered", "CRGStudyID")
#normalize_date_time("tblStudy", "DateEdited", "CRGStudyID")
#normalize_date_time("tblStudy", "DateToCENTRAL", "CRGStudyID")
#normalize_date_time("tblReport", "DateEdited", "CRGReportID")
#normalize_date_time("tblReport", "Dateentered", "CRGReportID")
#normalize_date_time("tblReport", "DatetoCENTRAL", "CRGReportID")
