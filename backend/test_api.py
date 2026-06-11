import traceback
import sys
from app.api.chat import ask_question, get_qdrant
from app.api.schemas import ChatRequest
from app.database.database import SessionLocal
from app.models import models
from app.embeddings.metadata_embedder import MetadataEmbedder

def test():
    db = SessionLocal()
    user = db.query(models.User).first()
    connection = db.query(models.ERPConnection).filter_by(tenant_id=user.tenant_id).first()
    
    if not connection:
        print("No ERP Connection found.")
        return

    print(f"Using Connection: {connection.name} (ID: {connection.id})")

    embedder = MetadataEmbedder()
    query_vector = embedder.embed_text('what are the item we using')
    qdrant = get_qdrant()
    search_results = qdrant.search_relevant_tables(
        tenant_id=user.tenant_id,
        connection_id=connection.id,
        query_vector=query_vector,
        limit=5
    )
    print("--- Qdrant Search Results ---")
    schema_context = ""
    for hit in search_results:
        payload = hit.payload
        print("Found Table:", payload['table_name'])
        schema_context += f"Table: {payload['table_name']}\nDescription: {payload['description']}\nColumns: {payload['columns']}\n\n"

    print("\n--- Schema Context ---")
    print(schema_context if schema_context else "No relevant tables found.")

    req = ChatRequest(connection_id=connection.id, question='what are the item we using')
    try:
        print("\nSending query to ask_question...")
        res = ask_question(req, db, user)
        print("\n--- LLM Response ---")
        print("SQL:", res.get("sql"))
        print("Data size:", len(res.get("data", [])))
        if res.get("data"):
            print("First row:", res.get("data")[0])
    except Exception as e:
        print("Error:")
        traceback.print_exc(file=sys.stdout)

if __name__ == "__main__":
    test()
