import os
import pandas as pd
from dotenv import load_dotenv
import psycopg

load_dotenv(dotenv_path=".env", override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

print("DATABASE_URL loaded?", bool(DATABASE_URL))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Check .env parsing/path.")

with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("select now();")
        print("Connected! Server time:", cur.fetchone()[0])

with psycopg.connect(DATABASE_URL) as conn:
    df = pd.read_sql_query('SELECT * FROM public.feedback LIMIT 10;', conn)
    print(df)