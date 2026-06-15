from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database.database import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    users = relationship("User", back_populates="tenant")
    erp_connections = relationship("ERPConnection", back_populates="tenant")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="users")
    user_roles = relationship("UserRole", back_populates="user")
    chat_history = relationship("ChatHistory", back_populates="user")

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    
    user_roles = relationship("UserRole", back_populates="role")
    permissions = relationship("RolePermission", back_populates="role")

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False) # e.g., 'view_dashboard', 'manage_erp'
    
    roles = relationship("RolePermission", back_populates="permission")

class RolePermission(Base):
    __tablename__ = "role_permissions"
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"))
    permission_id = Column(Integer, ForeignKey("permissions.id"))

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_id = Column(Integer, ForeignKey("roles.id"))

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")

class ERPConnection(Base):
    __tablename__ = "erp_connections"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    name = Column(String(255))
    db_type = Column(String(50)) # mysql, postgresql, sqlserver
    server = Column(String(255))
    database_name = Column(String(255))
    username = Column(String(255))
    encrypted_password = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="erp_connections")
    tables = relationship("MetadataTable", back_populates="connection")

class MetadataTable(Base):
    __tablename__ = "metadata_tables"
    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("erp_connections.id"))
    table_name = Column(String(255), nullable=False)
    module_name = Column(String(100)) # e.g., Sales, Inventory
    description = Column(Text)
    
    connection = relationship("ERPConnection", back_populates="tables")
    columns = relationship("MetadataColumn", back_populates="table")

class MetadataColumn(Base):
    __tablename__ = "metadata_columns"
    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("metadata_tables.id"))
    column_name = Column(String(255), nullable=False)
    data_type = Column(String(100))
    is_primary_key = Column(Boolean, default=False)
    is_foreign_key = Column(Boolean, default=False)
    description = Column(Text)

    table = relationship("MetadataTable", back_populates="columns")

class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(50), index=True) # Groups multiple queries into one chat session
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    question = Column(Text, nullable=False)
    generated_sql = Column(Text)
    response_json = Column(JSON) # Stores summary, chart_type, data
    execution_time_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="chat_history")

class DashboardTemplate(Base):
    __tablename__ = "dashboard_templates"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    layout_config = Column(JSON) # UI layout configuration
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DashboardInstance(Base):
    __tablename__ = "dashboard_instances"
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("dashboard_templates.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    instance_config = Column(JSON)

class QueryLog(Base):
    __tablename__ = "query_logs"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    sql_query = Column(Text)
    status = Column(String(50)) # success, error, blocked
    error_message = Column(Text)
    executed_at = Column(DateTime(timezone=True), server_default=func.now())

class LLMSettings(Base):
    __tablename__ = "llm_settings"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    provider = Column(String(50)) # gemini, openai
    model_name = Column(String(100))
    api_key_encrypted = Column(String(500))
    temperature = Column(String(50))
