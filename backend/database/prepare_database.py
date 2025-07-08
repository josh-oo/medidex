import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()

DATABASE_VOLUME = os.getenv("DATABASE_VOLUME")


def normalize_date_time(tbl_name, column_name, id_column):

    # Connect to your SQLite database
    conn = sqlite3.connect(os.path.join(DATABASE_VOLUME,"meerkat.db"))
    cursor = conn.cursor()

    def format_to_iso(date_str):
        # Parse the date using datetime.strptime
        dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M:%S")
        
        # Return the formatted date in ISO 8601 format (YYYY-MM-DD)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Fetch data from the table
    cursor.execute(f"SELECT {id_column}, {column_name} FROM {tbl_name}")  # Replace with your actual table and column names
    rows = cursor.fetchall()

    # Loop over the fetched rows, apply the format_date function, and update the table
    for row in rows:
        row_id = row[0]  # The unique row ID (to update the correct row)
        date_column = row[1]  # The original date value
        
        # Format the date
        formatted_date = format_to_iso(date_column)
        
        # Update the date in the database
        query = f"UPDATE {tbl_name} SET {column_name} = ? WHERE {id_column} = ?"
        cursor.execute(query, (formatted_date, row_id))

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

normalize_date_time("tblStudy", "DateEntered", "CRGStudyID")
normalize_date_time("tblReport", "Dateentered", "CRGReportID")
