from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from jose import JWTError, jwt

from ..database.database import get_db
from ..models import models
from . import schemas
from ..auth.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    get_current_user,
    SECRET_KEY,
    ALGORITHM
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # 1. Create Tenant
    tenant_name = user_data.tenant_name or f"{user_data.full_name}'s Tenant"
    tenant = models.Tenant(name=tenant_name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # 2. Hash password & Create User
    hashed_password = get_password_hash(user_data.password)
    new_user = models.User(
        email=user_data.email,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        tenant_id=tenant.id,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Clone default ERP connections from tenant 1 to the new tenant
    default_conns = db.query(models.ERPConnection).filter(models.ERPConnection.tenant_id == 1).all()
    for conn in default_conns:
        cloned_conn = models.ERPConnection(
            tenant_id=tenant.id,
            name=conn.name,
            db_type=conn.db_type,
            server=conn.server,
            database_name=conn.database_name,
            username=conn.username,
            encrypted_password=conn.encrypted_password,
            is_active=conn.is_active
        )
        db.add(cloned_conn)
    db.commit()

    # 3. Assign Default Role (Manager)
    manager_role = db.query(models.Role).filter(models.Role.name == "Manager").first()
    if manager_role:
        user_role = models.UserRole(user_id=new_user.id, role_id=manager_role.id)
        db.add(user_role)
        db.commit()

    # Build response containing role names
    roles = [manager_role.name] if manager_role else []
    
    # Return UserResponse matching schema
    return schemas.UserResponse(
        id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        tenant_id=new_user.tenant_id,
        is_active=new_user.is_active,
        roles=roles
    )

@router.post("/login", response_model=schemas.Token)
def login_user(login_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    # Generate tokens
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    
    return schemas.Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.post("/swagger-login", response_model=schemas.Token, include_in_schema=False)
def swagger_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
    
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    
    return schemas.Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@router.post("/refresh", response_model=schemas.Token)
def refresh_token(refresh_data: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(refresh_data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        if email is None or token_type != "refresh":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
    
    # Generate new access token and reuse the refresh token
    new_access_token = create_access_token(data={"sub": user.email})
    
    return schemas.Token(
        access_token=new_access_token,
        refresh_token=refresh_data.refresh_token,
        token_type="bearer"
    )

@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    roles = [ur.role.name for ur in current_user.user_roles if ur.role]
    return schemas.UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        tenant_id=current_user.tenant_id,
        is_active=current_user.is_active,
        roles=roles
    )
