"""
Controller de autenticação
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from services.auth_service import authenticate_user, create_access_token, get_current_user, get_db
from config.security import pwd_context
from models import User

router = APIRouter()


class UserCredentials(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(credentials: UserCredentials, db: Session = Depends(get_db)):
    """Rota de login"""
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"name": user.username})
    return {"access_token": access_token, "token_type": "bearer", "name": user.username, "id": user.id}


@router.post("/register")
def register(credentials: UserCredentials, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rota de registro (protegida)"""
    existing_user = db.query(User).filter(User.username == credentials.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = pwd_context.hash(credentials.password)
    new_user = User(username=credentials.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": f"User '{credentials.username}' successfully registered."} 