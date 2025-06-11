from sqlalchemy import Boolean, create_engine, Column, Integer, String, Float, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from sqlalchemy.orm import sessionmaker, relationship

# Conexão com o SQLite
DATABASE_URL = "sqlite:///./data/app.db"

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
    gps_status = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class DeviceLocation(Base):
    __tablename__ = "device_location"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    speed = Column(Float)
    hdop = Column(Float)
    sats = Column(Integer)
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

# Dynamic camera models
class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    ip_address = Column(String, nullable=False)
    port = Column(Integer, default=80)
    enabled_alerts = Column(JSON)  # List of enabled alert types
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with camera status
    statuses = relationship("CameraStatus", back_populates="camera")

class CameraStatus(Base):
    __tablename__ = "camera_status"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    is_connected = Column(Boolean, default=False)
    last_ping_time = Column(DateTime)
    response_time_ms = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationship with camera
    camera = relationship("Camera", back_populates="statuses")

class AlertType(Base):
    __tablename__ = "alert_types"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)  # NO_HELMET, NO_GLOVES, etc.
    name = Column(String, nullable=False)
    description = Column(String)
    icon = Column(String, default="Warning")  # Material-UI icon name
    color = Column(String, default="#ff9800")  # Hex color for the alert
    severity = Column(String, default="medium")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CameraAlert(Base):
    __tablename__ = "camera_alerts"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"), nullable=False)
    alert_type_id = Column(Integer, ForeignKey("alert_types.id"), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow, index=True)
    alert_metadata = Column(JSON)  # Additional data like bounding boxes, etc.
    resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    camera = relationship("Camera")
    alert_type = relationship("AlertType")
    resolved_by_user = relationship("User")