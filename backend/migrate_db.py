import sqlalchemy
import urllib.parse
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add app to path so we can import models
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.models import models
from app.database.database import Base

sqlite_url = "sqlite:///./edip.db"
pwd = urllib.parse.quote_plus("Tr@d3w@63")
mysql_url = f"mysql+pymysql://root:{pwd}@100.86.181.18:3309/Tradeware"

sqlite_engine = sqlalchemy.create_engine(sqlite_url)
mysql_engine = sqlalchemy.create_engine(mysql_url)

print("Creating tables in MySQL Tradeware database...")
# Create tables in MySQL based on our models
Base.metadata.create_all(bind=mysql_engine)

SqliteSession = sessionmaker(bind=sqlite_engine)
MysqlSession = sessionmaker(bind=mysql_engine)

sqlite_session = SqliteSession()
mysql_session = MysqlSession()

tables_to_migrate = [
    models.Tenant,
    models.User,
    models.ERPConnection,
    models.QueryLog,
    models.ChatHistory
]

try:
    for table in tables_to_migrate:
        print(f"Migrating {table.__name__}...")
        records = sqlite_session.query(table).all()
        for record in records:
            # We must make a copy of the object that isn't bound to the sqlite session
            mysql_session.merge(record)
        mysql_session.commit()
        print(f"Successfully migrated {len(records)} records for {table.__name__}.")
    print("Migration complete!")
except Exception as e:
    mysql_session.rollback()
    print(f"Migration failed: {e}")
finally:
    sqlite_session.close()
    mysql_session.close()
