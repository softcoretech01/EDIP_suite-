"""
ERP Schema Re-Indexer — uses deterministic integer IDs so re-runs
always overwrite existing points (no duplicates ever).
"""
import sys
import json
import os
import hashlib

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("d:/EDIP Suite/backend"))

from app.embeddings.metadata_embedder import MetadataEmbedder
from app.vector_db.qdrant_service import get_qdrant_client, create_collection
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue

TENANT_ID = 1
CONNECTION_ID = 2
COLLECTION_NAME = "erp_metadata"
CATALOG_FILE = "d:/EDIP Suite/backend/erp_qdrant_payloads.json"


def make_point_id(tenant_id: int, connection_id: int, table_name: str) -> int:
    """Deterministic integer ID — same table always gets the same ID."""
    key = f"{tenant_id}:{connection_id}:{table_name}"
    return int(hashlib.md5(key.encode()).hexdigest()[:15], 16)


def main():
    print("ERP Schema Re-Indexer (Deterministic IDs)")
    print("=" * 60)

    # 1. Load rich catalog
    print(f"\nLoading catalog: {CATALOG_FILE}")
    with open(CATALOG_FILE, encoding="utf-8") as f:
        payloads = json.load(f)
    print(f"Loaded {len(payloads)} table definitions")

    # 2. Init embedder
    print("\nLoading embedding model...")
    embedder = MetadataEmbedder()
    print("Embedding model ready.")

    # 3. Init Qdrant
    print("\nConnecting to Qdrant...")
    client = get_qdrant_client()
    create_collection(client, COLLECTION_NAME, vector_size=384)
    print(f"Connected. Collection: '{COLLECTION_NAME}'")

    # 4. Upsert all tables with deterministic IDs
    print(f"\nUpserting {len(payloads)} tables (overwrite-safe)...")
    success = 0
    errors = 0

    for i, doc in enumerate(payloads):
        table_name = doc.get("table_name", "unknown")
        vector_text = doc.get("vector_text", "")
        try:
            vector = embedder.embed_text(vector_text)
            point_id = make_point_id(TENANT_ID, CONNECTION_ID, table_name)
            point = PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "tenant_id": TENANT_ID,
                    "connection_id": CONNECTION_ID,
                    "table_name": table_name,
                    "description": doc.get("description", ""),
                    "columns": doc.get("columns", ""),
                    "erp_module": doc.get("erp_module", ""),
                    "primary_key": doc.get("primary_key", ""),
                    "foreign_keys": doc.get("foreign_keys", ""),
                    "example_queries": doc.get("example_queries", []),
                    "schema": doc.get("schema", ""),
                }
            )
            client.upsert(collection_name=COLLECTION_NAME, wait=True, points=[point])
            print(f"  [{i+1:02d}/{len(payloads)}] OK  : {table_name}")
            success += 1
        except Exception as e:
            print(f"  [{i+1:02d}/{len(payloads)}] FAIL: {table_name} — {e}")
            errors += 1

    # 5. Verify
    print(f"\n{'='*60}")
    print(f"DONE: {success} indexed, {errors} errors")
    info = client.get_collection(COLLECTION_NAME)
    count = info.points_count
    status = "CLEAN" if count == len(payloads) else f"WARNING: expected {len(payloads)}"
    print(f"Total points in Qdrant: {count} [{status}]")

    # 6. Search quality tests
    TESTS = [
        "how many local purchases this month",
        "top customers by revenue this year",
        "which items are low on stock",
        "what is our total import landed cost",
        "purchase requisitions not converted to PO",
        "which supplier do we buy from most",
    ]
    print("\n--- Semantic Search Quality Tests ---")
    for q in TESTS:
        print(f"\n  Query: '{q}'")
        vec = embedder.embed_text(q)
        res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            query_filter=Filter(must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=TENANT_ID)),
                FieldCondition(key="connection_id", match=MatchValue(value=CONNECTION_ID)),
            ]),
            limit=3
        )
        for r in res.points:
            print(f"    [{r.score:.4f}] {r.payload.get('table_name')} ({r.payload.get('erp_module')})")


if __name__ == "__main__":
    main()
