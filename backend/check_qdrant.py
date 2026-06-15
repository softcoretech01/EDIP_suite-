from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

client = QdrantClient(url="http://localhost:6333")
points, _ = client.scroll(collection_name="erp_schemas", limit=100)
for p in points:
    print(p.payload.get("table_name"))
