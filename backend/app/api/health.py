from fastapi import APIRouter
from app.database.mysql import test_connection as test_mysql
from app.vector_db.qdrant_service import test_qdrant_connection

router = APIRouter(
    prefix="/health",
    tags=["health checks"],
)

@router.get("/database")
def health_database():
    """
    Checks the connection status of all required databases (MySQL and Qdrant).
    """
    mysql_health = test_mysql()
    qdrant_health = test_qdrant_connection()

    response = {
        "mysql": mysql_health.get("status", "unknown"),
        "qdrant": qdrant_health.get("status", "unknown"),
        "details": {
            "mysql": mysql_health,
            "qdrant": qdrant_health
        }
    }
    
    # Optional: if you strictly want ONLY {"mysql": "connected", "qdrant": "connected"}
    # You can return just that, but having details helps in debugging.
    
    return {
        "mysql": mysql_health.get("status", "unknown"),
        "qdrant": qdrant_health.get("status", "unknown")
    }
