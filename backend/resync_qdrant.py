"""
resync_qdrant.py
----------------
Re-fetches live column definitions from ALL Tradeware schemas and upserts them
into Qdrant so the AI always sees accurate schema on the FIRST query attempt.

Run once after schema changes:
    python resync_qdrant.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import urllib.parse
from sqlalchemy import create_engine, text
from app.vector_db.qdrant_service import QdrantService
from app.embeddings.metadata_embedder import MetadataEmbedder
from app.database.database import SessionLocal
from app.models import models

# ── Config ────────────────────────────────────────────────────────────────────
SCHEMAS = ["Sales_Masters", "Purchase_Masters", "masters"]
HOST    = "100.86.181.18"
PORT    = 3309
USER    = "root"
PWD     = "Tr@d3w@63"
TENANT_NAME     = "Default Tenant"
CONNECTION_NAME = "Tradeware Live DB"
# ─────────────────────────────────────────────────────────────────────────────

def get_tenant_and_connection():
    db = SessionLocal()
    try:
        tenant = db.query(models.Tenant).filter_by(name=TENANT_NAME).first()
        connection = db.query(models.ERPConnection).filter_by(name=CONNECTION_NAME).first()
        if not tenant:
            raise RuntimeError(f"Tenant '{TENANT_NAME}' not found. Check TENANT_NAME.")
        if not connection:
            raise RuntimeError(f"ERP Connection '{CONNECTION_NAME}' not found. Check CONNECTION_NAME.")
        return tenant.id, connection.id
    finally:
        db.close()


def build_engine(schema: str):
    pwd_enc = urllib.parse.quote_plus(PWD)
    url = f"mysql+pymysql://{USER}:{pwd_enc}@{HOST}:{PORT}/{schema}"
    return create_engine(url, connect_args={"connect_timeout": 60})


def main():
    print("Fetching tenant/connection IDs from EDIP DB...")
    tenant_id, connection_id = get_tenant_and_connection()
    print(f"  tenant_id={tenant_id}  connection_id={connection_id}")

    qdrant   = QdrantService()
    embedder = MetadataEmbedder()

    total = 0
    for schema in SCHEMAS:
        print(f"\n[{schema}] Connecting...")
        try:
            engine = build_engine(schema)
            with engine.connect() as conn:
                tables = [row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()]
                print(f"  Found {len(tables)} tables: {tables}")

                for table_name in tables:
                    # Get columns with types
                    col_rows = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`")).fetchall()
                    columns_str = ", ".join(f"{r[0]} ({r[1]})" for r in col_rows)

                    # Build a rich description the embedder can use for semantic search
                    description = (
                        f"Table {schema}.{table_name} stores {table_name.replace('_', ' ').lower()} data. "
                        f"Columns: {columns_str}"
                    )

                    full_text = f"Table {schema}.{table_name}\nDescription: {description}\nColumns: {columns_str}"
                    vector = embedder.embed_text(full_text)

                    qdrant.upsert_table_metadata(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        table_name=f"{schema}.{table_name}",
                        description=description,
                        columns=columns_str,
                        vector=vector,
                    )
                    print(f"  OK {schema}.{table_name}  ({len(col_rows)} cols)")
                    total += 1

        except Exception as e:
            print(f"  x ERROR on schema {schema}: {e}")

    print(f"\nDone. {total} tables synced to Qdrant.")


if __name__ == "__main__":
    main()
