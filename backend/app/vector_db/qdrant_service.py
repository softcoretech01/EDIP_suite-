import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)

# Fetch Qdrant configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

def get_qdrant_client() -> QdrantClient:
    """
    Initializes and returns a QdrantClient based on environment variables.
    Supports both local and cloud Qdrant connections.
    """
    try:
        if QDRANT_HOST == "localhost" or QDRANT_HOST == "127.0.0.1":
            # Using memory/local server for development if API key is not set
            if not QDRANT_API_KEY:
                # Use persistent local file storage (as before) to ensure backward compatibility
                db_path = os.path.join(os.path.dirname(__file__), "local_qdrant")
                return QdrantClient(path=db_path)
            
        # Cloud or external server connection
        client = QdrantClient(
            url=f"http://{QDRANT_HOST}:{QDRANT_PORT}",
            api_key=QDRANT_API_KEY if QDRANT_API_KEY else None,
            timeout=10
        )
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant client: {e}")
        raise

def test_qdrant_connection() -> dict:
    """
    Health check function to verify Qdrant connection.
    """
    try:
        client = get_qdrant_client()
        # Ping by trying to list collections
        client.get_collections()
        return {"status": "connected", "details": f"Connected to Qdrant at {QDRANT_HOST}"}
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Qdrant connection test failed: {error_msg}")
        return {"status": "disconnected", "error": error_msg}

def collection_exists(client: QdrantClient, collection_name: str) -> bool:
    """
    Checks if a specific collection exists in Qdrant.
    """
    try:
        client.get_collection(collection_name=collection_name)
        return True
    except (UnexpectedResponse, ValueError):
        return False
    except Exception as e:
        logger.warning(f"Error checking collection existence: {e}")
        return False

def create_collection(client: QdrantClient, collection_name: str, vector_size: int = 384):
    """
    Creates a new collection in Qdrant.
    """
    try:
        if not collection_exists(client, collection_name):
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info(f"Collection '{collection_name}' created successfully.")
    except Exception as e:
        logger.error(f"Failed to create collection '{collection_name}': {e}")
        raise

def list_collections(client: QdrantClient) -> List[str]:
    """
    Returns a list of all collection names in Qdrant.
    """
    try:
        response = client.get_collections()
        return [col.name for col in response.collections]
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise

def delete_collection(client: QdrantClient, collection_name: str):
    """
    Deletes a collection from Qdrant.
    """
    try:
        client.delete_collection(collection_name=collection_name)
        logger.info(f"Collection '{collection_name}' deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete collection '{collection_name}': {e}")
        raise

class QdrantService:
    """
    Service class to encapsulate EDIP Suite specific operations.
    Maintains backward compatibility with chat functionality.
    """
    def __init__(self):
        self.client = get_qdrant_client()
        self.collection_name = "erp_metadata"
        create_collection(self.client, self.collection_name)

    def upsert_table_metadata(self, tenant_id: int, connection_id: int, table_name: str, description: str, columns: list, vector: list):
        """
        Store a table's metadata and its embedding.
        """
        payload = {
            "tenant_id": tenant_id,
            "connection_id": connection_id,
            "table_name": table_name,
            "description": description,
            "columns": columns # List of column names/types
        }
        
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload
        )
        
        self.client.upsert(
            collection_name=self.collection_name,
            wait=True,
            points=[point]
        )

    def search_relevant_tables(self, tenant_id: int, connection_id: int, query_vector: list, limit: int = 5):
        """
        Search for tables relevant to a user query within a specific tenant and connection.
        """
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                    FieldCondition(key="connection_id", match=MatchValue(value=connection_id))
                ]
            ),
            limit=limit
        )
        return search_result.points
