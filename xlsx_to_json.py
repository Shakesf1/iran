import pandas as pd
import re
import json
import base64
import os
from datetime import date
from supabase import create_client, Client
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY = "pay_homage_to_stan_4ever"

def encrypt_data(data_string, key=SECRET_KEY):
    xor_data = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data_string))
    encoded = base64.b64encode(xor_data.encode('utf-8')).decode('utf-8')
    return encoded

# Read both header rows
# This handles split/merged headers
# If you have more than 2 header rows, adjust header=[0,1]
df = pd.read_excel('TankerTrackers.xlsx', engine='openpyxl', header=[0, 1])

def flatten_col(col):
    # Join non-empty parts, strip spaces
    return ' '.join([str(c).strip() for c in col if str(c).strip() and str(c).strip() != 'nan'])

# Flatten MultiIndex columns
# This will give you e.g. 'Name (IMO)', 'UANI', 'OFAC', etc.
df.columns = [flatten_col(col) for col in df.columns]

# Drop columns with 'Unnamed' in their name
df = df[[col for col in df.columns if not col.startswith('Unnamed')]]

def extract_imo(name):
    if pd.isna(name):
        return None
    match = re.search(r'\((\d{6,8})\)', str(name))
    if match:
        return match.group(1)
    return None

# Add IMO column
if 'Name (IMO)' in df.columns:
    df['imo'] = df['Name (IMO)'].apply(extract_imo)
else:
    # Try to find the column that contains 'IMO' in its name
    name_col = [c for c in df.columns if 'IMO' in c][0]
    df['imo'] = df[name_col].apply(extract_imo)

df.columns = ['Name (IMO)', 'YearBuilt', 'ClassSize', 'Flag', 'OFAC', 'FCDO', 'UANI', 'EU', 'ASO', 'MFAT', 'GAC', 'SECO', 'UN', 'IMO']
df.columns = [col.lower() for col in df.columns]
print(df.head())  # Check the first few rows to ensure IMO is extracted correctly

# Convert all values to string or None for JSON serialization
def safe_convert(val):
    if pd.isna(val):
        return None
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)

# Rename columns to match Supabase table schema
rename_map = {
    'name (imo)': 'name_imo',
    'yearbuilt': 'yearbuilt',
    'classsize': 'classsize',
    'flag': 'flag',
    'ofac': 'ofac',
    'fcdo': 'fcdo',
    'uani': 'uani',
    'eu': 'eu',
    'aso': 'aso',
    'mfat': 'mfat',
    'gac': 'gac',
    'seco': 'seco',
    'un': 'un',
    'imo': 'imo'
}
df = df.rename(columns=rename_map)

records = [ {k: safe_convert(v) for k, v in row.items()} for row in df.to_dict(orient='records') ]

raw_json_str = json.dumps(records, indent=2)

with open('TankerTrackers.json', 'w') as f:
    json.dump({"payload": encrypt_data(raw_json_str)}, f)
print(f"Exported {len(records)} records to TankerTrackers.json (encrypted)")

# Setup Supabase client (reuse .env or set env vars SUPABASE_URL, SUPABASE_KEY)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

table_name = "tanker_trackers"
today = date.today().isoformat()

# Add today's date to each record
for rec in records:
    rec["record_date"] = today

# Delete existing records with today's date
print(f"Deleting existing records in '{table_name}' with record_date = {today} ...")
supabase.table(table_name).delete().eq("record_date", today).execute()

# Insert new records
print(f"Inserting {len(records)} records into '{table_name}' ...")
supabase.table(table_name).insert(records).execute()
print("Supabase insert complete.")
