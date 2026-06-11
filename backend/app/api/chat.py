from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import sqlalchemy
import time
from typing import List, Dict, Any

from ..database.database import get_db
from ..models import models
from . import schemas
from ..auth.auth import get_current_user
from ..vector_db.qdrant_service import QdrantService
from ..embeddings.metadata_embedder import MetadataEmbedder
from ..services.gemini_service import GeminiService
from ..services.sql_validator import SQLValidator
from .erp_connections import build_connection_string

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)
# Lazy initialization for Qdrant to avoid uvicorn --reload lock issues
_qdrant_service = None

# Global Engine Cache to prevent TCP handshake latency on every query
_engine_cache = {}

def get_engine(connection_url: str):
    if connection_url not in _engine_cache:
        # pool_pre_ping ensures stale connections are re-established transparently
        _engine_cache[connection_url] = sqlalchemy.create_engine(connection_url, pool_pre_ping=True)
    return _engine_cache[connection_url]

def get_qdrant():
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
embedder = MetadataEmbedder()
gemini_service = GeminiService()

@router.post("/ask")
def ask_question(request: schemas.ChatRequest, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    try:
        start_time = time.time()
        
        # 1. Get ERP Connection
        connection = db.query(models.ERPConnection).filter(
            models.ERPConnection.id == request.connection_id,
            models.ERPConnection.tenant_id == current_user.tenant_id
        ).first()
        
        if not connection:
            raise HTTPException(status_code=404, detail="ERP Connection not found")

        # 2. Embed the question
        query_vector = embedder.embed_text(request.question)

        # 3. Retrieve relevant schema from Qdrant
        search_results = get_qdrant().search_relevant_tables(
            tenant_id=current_user.tenant_id,
            connection_id=connection.id,
            query_vector=query_vector,
            limit=5
        )
        
        schema_context = ""
        for hit in search_results:
            payload = hit.payload
            schema_context += f"Table: {payload['table_name']}\nDescription: {payload['description']}\nColumns: {payload['columns']}\n\n"

        if not schema_context:
            schema_context = "No relevant tables found. Please check metadata."

        # 4. Generate SQL using Gemini
        try:
            llm_response = gemini_service.generate_sql_and_dashboard(request.question, schema_context)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "ResourceExhausted" in error_str or "quota" in error_str.lower():
                print(f"RATE LIMIT HIT: {error_str}")
                raise HTTPException(status_code=429, detail="Gemini API rate limit exceeded. You are on the free tier, please wait a minute before trying again.")
            
            import traceback
            raise HTTPException(status_code=500, detail=f"Gemini error: {traceback.format_exc()}")

        generated_sql = llm_response.get("sql", "")
        
        if not generated_sql:
            # Fallback checks if LLM used a different key
            if "query" in llm_response:
                generated_sql = llm_response["query"]
            elif "SQL" in llm_response:
                generated_sql = llm_response["SQL"]
                
        if not generated_sql:
            raise HTTPException(status_code=400, detail=f"LLM failed to generate a SQL query. Response received: {llm_response}")

        # 5. Validate SQL
        is_safe, reason = SQLValidator.is_safe_query(generated_sql)
        if not is_safe:
            # Log blocked query
            log = models.QueryLog(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                sql_query=generated_sql,
                status="blocked",
                error_message=reason
            )
            db.add(log)
            db.commit()
            raise HTTPException(status_code=403, detail=f"Query blocked by security policy: {reason}")

        # 6. Execute SQL
        connection_url = build_connection_string(
            schemas.TestConnectionRequest(
                db_type=connection.db_type,
                server=connection.server,
                database_name=connection.database_name,
                username=connection.username,
                password=connection.encrypted_password.replace("enc_", "") # Demock
            )
        )
        
        try:
            engine = get_engine(connection_url)
            with engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(generated_sql))
                columns = result.keys()
                data = [dict(zip(columns, row)) for row in result.fetchall()]
                
                # Convert datetime/decimals to string for JSON serialization
                for row in data:
                    for k, v in row.items():
                        if not isinstance(v, (int, float, str, bool, type(None))):
                            row[k] = str(v)
                
                llm_response["data"] = data
                
                # 6.5 Synthesize Data into Conversational Response
                if data and request.view_mode != "dashboard":
                    conversational_summary = gemini_service.synthesize_data(request.question, data)
                    llm_response["summary"] = conversational_summary
                
            # Log successful query
            log = models.QueryLog(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                sql_query=generated_sql,
                status="success"
            )
            db.add(log)
            
        except Exception as e:
            # Log failed query
            import traceback
            log = models.QueryLog(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                sql_query=generated_sql,
                status="error",
                error_message=str(e)
            )
            db.add(log)
            db.commit()
            raise HTTPException(status_code=500, detail=f"Database execution error: {traceback.format_exc()}")

        # 7. Log chat history
        execution_time_ms = int((time.time() - start_time) * 1000)
        chat_history = models.ChatHistory(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            question=request.question,
            generated_sql=generated_sql,
            response_json=llm_response,
            execution_time_ms=execution_time_ms
        )
        db.add(chat_history)
        db.commit()

        return llm_response
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Unexpected error: {traceback.format_exc()}")

@router.get("/debug-qdrant")
def debug_qdrant():
    qdrant = get_qdrant()
    # Scroll through points to count
    points, _ = qdrant.client.scroll(collection_name=qdrant.collection_name, limit=100)
    conn_counts = {}
    for p in points:
        cid = p.payload.get("connection_id")
        conn_counts[cid] = conn_counts.get(cid, 0) + 1
    return {"total_points": len(points), "connection_counts": conn_counts}

@router.post("/force-sync")
def force_sync_qdrant(db: Session = Depends(get_db)):
    from sqlalchemy import create_engine, text
    import urllib.parse
    from app.embeddings.metadata_embedder import MetadataEmbedder
    from app.models import models
    import datetime

    tenant = db.query(models.Tenant).filter_by(name="Default Tenant").first()
    connection = db.query(models.ERPConnection).filter_by(name="Tradeware Live DB").first()
    
    qdrant = get_qdrant()
    embedder = MetadataEmbedder()
    
    schemas = ["Sales_Masters", "Purchase_Masters", "masters"]
    pwd = urllib.parse.quote_plus("Tr@d3w@63")
    
    count = 0
    for schema in schemas:
        tw_engine = create_engine(f"mysql+pymysql://root:{pwd}@100.86.181.18:3309/{schema}", connect_args={'connect_timeout': 30})
        with tw_engine.connect() as conn:
            tables_result = conn.execute(text("SHOW TABLES"))
            table_names = [row[0] for row in tables_result]
            
            for table_name in table_names:
                desc_result = conn.execute(text(f"SHOW CREATE TABLE `{table_name}`"))
                create_stmt = desc_result.fetchone()[1]
                
                cols_result = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`"))
                columns = []
                for row in cols_result:
                    columns.append(f"{row[0]} ({row[1]})")
                columns_str = ", ".join(columns)
                
                full_text = f"Table {schema}.{table_name}\nDescription: {create_stmt[:200]}\nColumns: {columns_str}"
                vector = embedder.embed_text(full_text)
                
                qdrant.upsert_table_metadata(
                    tenant_id=tenant.id,
                    connection_id=connection.id,
                    table_name=f"{schema}.{table_name}",
                    description="Synced from live DB",
                    columns=columns_str,
                    vector=vector
                )
                count += 1
    return {"status": "success", "tables_synced": count}
