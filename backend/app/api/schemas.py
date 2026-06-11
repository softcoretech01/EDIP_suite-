from pydantic import BaseModel
from typing import List, Optional

class ERPConnectionBase(BaseModel):
    name: str
    db_type: str
    server: str
    database_name: str
    username: str

class ERPConnectionCreate(ERPConnectionBase):
    password: str

class ERPConnectionResponse(ERPConnectionBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class TestConnectionRequest(BaseModel):
    db_type: str
    server: str
    database_name: str
    username: str
    password: str

class ChatRequest(BaseModel):
    connection_id: int
    question: str
    view_mode: Optional[str] = "chat"
