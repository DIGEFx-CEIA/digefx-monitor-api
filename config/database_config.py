"""
Configuração do banco de dados
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .app_config import app_config

# Configurações do banco de dados
DATABASE_URL = app_config.get_database_url()

# Configuração da engine do SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
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


def create_tables():
    """Cria as tabelas no banco de dados"""
    from models import Base as ModelsBase
    ModelsBase.metadata.create_all(bind=engine)
    print("✅ Tabelas do banco de dados criadas com sucesso")


def drop_tables():
    """Remove todas as tabelas do banco de dados"""
    from models import Base as ModelsBase
    ModelsBase.metadata.drop_all(bind=engine)
    print("❌ Tabelas do banco de dados removidas")


def reset_database():
    """Reseta o banco de dados (remove e recria tabelas)"""
    drop_tables()
    create_tables()
    print("🔄 Banco de dados resetado com sucesso") 