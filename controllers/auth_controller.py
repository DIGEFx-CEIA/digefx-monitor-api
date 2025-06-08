"""
Controller de autenticação
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from config.security import security, verify_password, create_access_token, get_current_user
from config.database_config import get_database
from models import User

router = APIRouter()


class UserCredentials(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    name: str
    id: int


class RegisterResponse(BaseModel):
    message: str


def authenticate_user(db: Session, username: str, password: str):
    """Autentica usuário"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


@router.post("/login", response_model=LoginResponse)
def login(credentials: UserCredentials, db: Session = Depends(get_database)):
    """Fazer login e obter token JWT"""
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"name": user.username})
    return LoginResponse(
        access_token=access_token, 
        token_type="bearer", 
        name=user.username, 
        id=user.id
    )


@router.post("/register", response_model=RegisterResponse, dependencies=[Depends(security)])
def register(credentials: UserCredentials, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Registrar novo usuário (protegida)"""
    from config.security import get_password_hash
    
    existing_user = db.query(User).filter(User.username == credentials.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = get_password_hash(credentials.password)
    new_user = User(username=credentials.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return RegisterResponse(message=f"User '{credentials.username}' successfully registered.") 