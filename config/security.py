"""
Configurações de segurança da aplicação
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Optional

from .app_config import app_config
from .database_config import get_database

# Configuração de hash de senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme para Swagger
security = HTTPBearer(scheme_name="BearerAuth")

# Configurações JWT
SECRET_KEY = app_config.get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = app_config.ACCESS_TOKEN_EXPIRE_MINUTES


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha está correta"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Gera hash da senha"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria token JWT"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extrai e valida o token JWT"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("name")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception


def get_current_user(token: str = Depends(get_current_user_token), db: Session = Depends(get_database)):
    """Obtém o usuário atual a partir do token"""
    from models import User  # Import here to avoid circular import
    
    user = db.query(User).filter(User.username == token).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user 