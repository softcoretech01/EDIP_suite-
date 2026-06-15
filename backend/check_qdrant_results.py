"""Check what tables Qdrant knows about and verify Invoice_Header is there."""
import sys
sys.path.insert(0, '.')

from app.vector_db.qdrant_service import QdrantService
from app.embeddings.metadata_embedder import MetadataEmbedder

qdrant = QdrantService()
embedder = MetadataEmbedder()

# Search for invoice-related tables
test_queries = [
    "which invoice has high value",
    "top selling items",
    "purchase requisition PR-001",
    "stock level inventory",
    "customer list",
]

for q in test_queries:
    vec = embedder.embed_text(q)
    results = qdrant.search_relevant_tables(tenant_id=1, connection_id=1, query_vector=vec, limit=3)
    print(f"\nQuery: '{q}'")
    for r in results:
        print(f"  -> {r.payload.get('table_name')} (score: {r.score:.3f})")
