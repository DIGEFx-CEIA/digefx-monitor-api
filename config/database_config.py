"""
Configuração do banco de dados
"""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .app_config import app_config
from models import AlertType, Base as ModelsBase, User
from passlib.context import CryptContext

# Configurações do banco de dados
DATABASE_URL = app_config.get_database_url()

# Configuração da engine do SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_size=20,           # Aumentar pool base
    max_overflow=30,        # Aumentar overflow
    pool_timeout=60,        # Aumentar timeout
    pool_recycle=3600,      # Reciclar conexões a cada hora
    pool_pre_ping=True      # Verificar conexões antes de usar
)

# Configuração da sessão
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para os modelos
Base = declarative_base()


def get_database():
    """Dependency para obter sessão do banco de dados"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Context manager para gerenciar sessões do banco de dados"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Cria as tabelas no banco de dados"""
    ModelsBase.metadata.create_all(bind=engine, checkfirst=True)
    create_default_user()
    create_default_alert_types()
    print("✅ Tabelas do banco de dados criadas com sucesso")

def create_default_user():
    """Cria usuário padrão admin/admin"""
    db = SessionLocal()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        print("Criando usuário padrão admin/admin")
        context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed_password = context.hash("admin")
        new_user = User(username="admin", hashed_password=hashed_password)
        db.add(new_user)
        db.commit()
    db.close()

def create_default_alert_types():
    """Create default alert types if they don't exist"""
    db = SessionLocal()
    try:
        default_alerts = [
            {
                "code": "NO_HELMET", 
                "name": "No Helmet Detected", 
                "description": "Person detected without safety helmet",
                "icon": "Construction",
                "color": "#f44336"
            },
            {
                "code": "NO_GLOVES", 
                "name": "No Gloves Detected", 
                "description": "Person detected without safety gloves",
                "icon": "FrontHand",
                "color": "#ff9800"
            },
            {
                "code": "NO_SEAT_BELT", 
                "name": "No Seat Belt", 
                "description": "Driver detected without seat belt",
                "icon": "AirlineSeatReclineNormal",
                "color": "#2196f3"
            },
            {
                "code": "SMOKING", 
                "name": "Smoking Detected", 
                "description": "Person detected smoking",
                "icon": "SmokingRooms",
                "color": "#9c27b0"
            },
            {
                "code": "USING_CELL_PHONE", 
                "name": "Cell Phone Usage", 
                "description": "Person detected using cell phone",
                "icon": "PhoneAndroid",
                "color": "#4caf50"
            },
        ]
        
        for alert_data in default_alerts:
            existing_alert = db.query(AlertType).filter(AlertType.code == alert_data["code"]).first()
            if not existing_alert:
                alert_type = AlertType(**alert_data)
                db.add(alert_type)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error creating default alert types: {e}")
    finally:
        db.close()


def drop_tables():
    """Remove todas as tabelas do banco de dados"""
    ModelsBase.metadata.drop_all(bind=engine)
    print("❌ Tabelas do banco de dados removidas")


def reset_database():
    """Reseta o banco de dados (remove e recria tabelas)"""
    drop_tables()
    create_tables()
    print("🔄 Banco de dados resetado com sucesso") 