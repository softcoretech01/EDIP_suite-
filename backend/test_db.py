from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv(override=True)

user = os.getenv("MYSQL_USERNAME")
pwd = os.getenv("MYSQL_PASSWORD")
host = os.getenv("MYSQL_HOST")
port = os.getenv("MYSQL_PORT")
db = os.getenv("MYSQL_DATABASE")

url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"
print(f"Connecting to {host}:{port}...")

try:
    engine = create_engine(url, connect_args={'connect_timeout': 5})
    with engine.connect() as conn:
        print("Success! Connected to Application Database.")
except Exception as e:
    print(f"Failed to connect: {e}")
