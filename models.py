from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from sqlalchemy.orm import sessionmaker

# Conexão com o SQLite
DATABASE_URL = "sqlite:///./database.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Modelo de Usuário
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class DeviceStatus(Base):
    __tablename__ = "device_status"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    ignition = Column(String)
    battery_voltage = Column(Float)
    min_voltage = Column(Float)
    relay1_status = Column(String)
    relay1_time = Column(Float)
    relay2_status = Column(String)
    relay2_time = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Criação do banco de dados e da tabela
Base.metadata.create_all(bind=engine)
