import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from ..database.database import get_db
from ..models import models

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key-for-edip-suite")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(db: Session = Depends(get_db)):
    # DEVELOPMENT MOCK: Return the first user in the database, or create one if none exists.
    # This bypasses the need for a JWT token while testing the frontend chat.
    user = db.query(models.User).first()
    if not user:
        tenant = db.query(models.Tenant).first()
        if not tenant:
            tenant = models.Tenant(name="Default Tenant")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
        user = models.User(email="dev@edip.com", hashed_password="mock", tenant_id=tenant.id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
