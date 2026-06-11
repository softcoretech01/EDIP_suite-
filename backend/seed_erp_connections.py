import os
import sqlalchemy
from sqlalchemy.orm import Session
from app.database.database import engine, SessionLocal
from app.models import models

def seed_connections():
    # Ensure tables are created
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Create a default tenant if it doesn't exist
        tenant = db.query(models.Tenant).filter_by(name="Default Tenant").first()
        if not tenant:
            tenant = models.Tenant(name="Default Tenant")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # Create ERP Connection to the Mock ERP DB we just generated
        connection = db.query(models.ERPConnection).filter_by(name="Mock ERP Local Database").first()
        if not connection:
            connection = models.ERPConnection(
                tenant_id=tenant.id,
                name="Mock ERP Local Database",
                db_type="sqlite",
                server="localhost",
                database_name="mock_erp.db",
                username="mock_user",
                encrypted_password="enc_mock_password"
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)

        print(f"Mock ERP Connection created with ID: {connection.id}")

        # Seed Metadata into Qdrant for the RAG engine
        from app.vector_db.qdrant_service import QdrantService
        from app.embeddings.metadata_embedder import MetadataEmbedder

        qdrant = QdrantService()
        embedder = MetadataEmbedder()

        metadata_records = [
            {
                "table_name": "sales",
                "description": "Contains records of all product sales, including quantities, dates, and total amounts.",
                "columns": "sale_id, customer_id, product_id, quantity, sale_date, total_amount"
            },
            {
                "table_name": "customers",
                "description": "Contains information about all customers, including their name and region.",
                "columns": "customer_id, name, region"
            },
            {
                "table_name": "products",
                "description": "Contains product catalog data, including category and pricing.",
                "columns": "product_id, name, category, price"
            }
        ]

        print("Embedding metadata and uploading to Qdrant...")
        for meta in metadata_records:
            # 1. Generate text to embed
            text_to_embed = f"Table: {meta['table_name']}\nDescription: {meta['description']}\nColumns: {meta['columns']}"
            
            # 2. Get vector from embedder
            vector = embedder.embed_text(text_to_embed)
            
            # 3. Store in Qdrant
            qdrant.upsert_table_metadata(
                tenant_id=tenant.id,
                connection_id=connection.id,
                table_name=meta["table_name"],
                description=meta["description"],
                columns=meta["columns"],
                vector=vector
            )

        print("Seeding complete! You are ready to query your Mock ERP Database!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_connections()
