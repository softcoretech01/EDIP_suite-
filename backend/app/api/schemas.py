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
    session_id: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    tenant_name: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    tenant_id: int
    is_active: bool
    roles: List[str] = []

    class Config:
        from_attributes = True

