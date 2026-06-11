import os
import urllib.parse
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import Session
from app.database.database import engine as edip_engine, SessionLocal
from app.models import models
from app.vector_db.qdrant_service import QdrantService
from app.embeddings.metadata_embedder import MetadataEmbedder

def sync_tradeware():
    db = SessionLocal()
    try:
        tenant = db.query(models.Tenant).first()
        if not tenant:
            tenant = models.Tenant(name="Default Tenant")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # 1. Add connection to EDIP Database
        conn_name = "Tradeware Live DB"
        connection = db.query(models.ERPConnection).filter_by(name=conn_name).first()
        if not connection:
            connection = models.ERPConnection(
                tenant_id=tenant.id,
                name=conn_name,
                db_type="mysql",
                server="100.86.181.18:3309",
                database_name="Tradeware",
                username="root",
                encrypted_password="enc_Tr@d3w@63" # Mock encryption
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)

        print(f"Tradeware Connection saved with ID: {connection.id}")

        # 2. Connect to MySQL and extract schemas
        print("Connecting to MySQL...")
        pwd = urllib.parse.quote_plus("Tr@d3w@63")
        
        qdrant = QdrantService()
        embedder = MetadataEmbedder()
        
        schemas = ["Sales_Masters", "Purchase_Masters", "masters"]
        
        for schema in schemas:
            print(f"Syncing schema: {schema}...")
            tw_engine = create_engine(f"mysql+pymysql://root:{pwd}@100.86.181.18:3309/{schema}", connect_args={'connect_timeout': 30})
            
            with tw_engine.connect() as conn:
                from sqlalchemy import text
                # Get tables
                tables_result = conn.execute(text("SHOW TABLES"))
                table_names = [row[0] for row in tables_result]
                print(f"Found {len(table_names)} tables in {schema}.")

                # Embed and upload to Qdrant
                count = 0
                for table_name in table_names:
                    # Get columns
                    desc_result = conn.execute(text(f"DESCRIBE `{table_name}`"))
                    col_details = []
                    for row in desc_result:
                        col_name = row[0]
                        col_type = row[1]
                        col_details.append(f"{col_name} ({col_type})")
                    
                    columns_str = ", ".join(col_details)
                    description = f"Table {table_name} from {schema} database."

                    text_to_embed = f"Table: {table_name}\nDatabase: {schema}\nDescription: {description}\nColumns: {columns_str}"
                    vector = embedder.embed_text(text_to_embed)
                    
                    qdrant.upsert_table_metadata(
                        tenant_id=tenant.id,
                        connection_id=connection.id,
                        table_name=f"{schema}.{table_name}",
                        description=description,
                        columns=columns_str,
                        vector=vector
                    )
                    count += 1
                    
                print(f"Finished embedding {count} tables from {schema}.")

        print("Successfully synced all Tradeware schemas to AI Engine!")

    except Exception as e:
        print(f"Error syncing Tradeware: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    sync_tradeware()
