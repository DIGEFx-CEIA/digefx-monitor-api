from sqlalchemy import Boolean, create_engine, Column, Integer, String, Float, DateTime
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
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
class HostStatus(Base):
    __tablename__ = "host_status"
    id = Column(Integer, primary_key=True, index=True)
    host_ip = Column(String, index=True)
    public_ip = Column(String)
    cpu_usage = Column(Float)
    ram_usage = Column(Float)
    disk_usage = Column(Float)
    temperature = Column(Float)
    online = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class CameraStatus(Base):
    __tablename__ = "camera_status"
    id = Column(Integer, primary_key=True, index=True)
    camera1_ip = Column(String, nullable=True)
    camera1_connected = Column(Boolean, default=False)
    camera2_ip = Column(String, nullable=True)
    camera2_connected = Column(Boolean, default=False)
    camera3_ip = Column(String, nullable=True)
    camera3_connected = Column(Boolean, default=False)
    camera4_ip = Column(String, nullable=True)
    camera4_connected = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

# Criação do banco de dados e da tabela
Base.metadata.create_all(bind=engine)
