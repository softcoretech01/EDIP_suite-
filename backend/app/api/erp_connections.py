from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database.database import get_db
from ..models import models
from . import schemas
from ..auth.auth import get_current_user
import sqlalchemy

router = APIRouter(
    prefix="/erp",
    tags=["erp_connections"],
)

def build_connection_string(req: schemas.TestConnectionRequest) -> str:
    import urllib.parse
    pwd = urllib.parse.quote_plus(req.password) if req.password else ""
    
    if req.db_type.lower() == "mysql":
        return f"mysql+pymysql://{req.username}:{pwd}@{req.server}/{req.database_name}"
    elif req.db_type.lower() == "postgresql":
        return f"postgresql+psycopg2://{req.username}:{pwd}@{req.server}/{req.database_name}"
    elif req.db_type.lower() == "sqlserver":
        return f"mssql+pyodbc://{req.username}:{pwd}@{req.server}/{req.database_name}?driver=ODBC+Driver+17+for+SQL+Server"
    elif req.db_type.lower() == "sqlite":
        # For sqlite, we ignore username/password and server
        # For mock_erp.db in the backend folder
        import os
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", req.database_name)
        # Normalize the path for SQLAlchemy
        db_path = os.path.abspath(db_path).replace("\\", "/")
        return f"sqlite:///{db_path}"
    else:
        raise ValueError(f"Unsupported database type: {req.db_type}")

@router.post("/test-connection")
def test_connection(req: schemas.TestConnectionRequest, current_user: models.User = Depends(get_current_user)):
    try:
        connection_url = build_connection_string(req)
        engine = sqlalchemy.create_engine(connection_url, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            # simple query to test
            conn.execute(sqlalchemy.text("SELECT 1"))
        return {"status": "success", "message": "Connection successful"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")

@router.post("/save-connection", response_model=schemas.ERPConnectionResponse)
def save_connection(conn_data: schemas.ERPConnectionCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Basic encryption mock for now - in production use cryptography fernet
    encrypted_pass = f"enc_{conn_data.password}" 
    
    new_conn = models.ERPConnection(
        tenant_id=current_user.tenant_id,
        name=conn_data.name,
        db_type=conn_data.db_type,
        server=conn_data.server,
        database_name=conn_data.database_name,
        username=conn_data.username,
        encrypted_password=encrypted_pass
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)
    return new_conn

@router.get("/connections", response_model=List[schemas.ERPConnectionResponse])
def get_connections(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    connections = db.query(models.ERPConnection).filter(models.ERPConnection.tenant_id == current_user.tenant_id).all()
    return connections
