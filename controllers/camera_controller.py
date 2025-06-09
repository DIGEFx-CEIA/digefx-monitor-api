"""
Controller de gerenciamento de câmeras
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List

from config.security import security, get_current_user
from config.database_config import get_database
from models import Camera, CameraStatus, AlertType, User
from schemas import (CameraCreate, CameraUpdate, CameraResponse, CameraListResponse, 
                    CameraStatusResponse, CameraStatusListResponse)

router = APIRouter(prefix="/cameras")


@router.get("", response_model=CameraListResponse, dependencies=[Depends(security)])
def get_cameras(current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Obter todas as câmeras"""
    cameras = db.query(Camera).all()
    camera_responses = [
        CameraResponse(
            id=camera.id,
            name=camera.name,
            ip_address=camera.ip_address,
            port=camera.port,
            enabled_alerts=camera.enabled_alerts or [],
            is_active=camera.is_active,
            created_at=camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
            updated_at=camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) for camera in cameras
    ]
    
    return CameraListResponse(cameras=camera_responses, total_count=len(camera_responses))


@router.get("/status", response_model=CameraStatusListResponse, dependencies=[Depends(security)])
def get_cameras_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Obter status mais recente de todas as câmeras"""
    # Get the latest status for each camera
    subquery = db.query(
        CameraStatus.camera_id,
        func.max(CameraStatus.timestamp).label('latest_timestamp')
    ).group_by(CameraStatus.camera_id).subquery()
    
    latest_statuses = db.query(CameraStatus).join(
        subquery,
        and_(
            CameraStatus.camera_id == subquery.c.camera_id,
            CameraStatus.timestamp == subquery.c.latest_timestamp
        )
    ).all()
    
    status_responses = []
    for status in latest_statuses:
        camera = db.query(Camera).filter(Camera.id == status.camera_id).first()
        if camera:
            status_responses.append(CameraStatusResponse(
                camera_id=camera.id,
                camera_name=camera.name,
                camera_ip=camera.ip_address,
                camera_port=camera.port,
                is_connected=status.is_connected,
                last_ping_time=status.last_ping_time.strftime("%Y-%m-%d %H:%M:%S GMT") if status.last_ping_time else None,
                response_time_ms=status.response_time_ms,
                timestamp=status.timestamp.strftime("%Y-%m-%d %H:%M:%S GMT")
            ))
    
    return CameraStatusListResponse(statuses=status_responses, total_count=len(status_responses))


@router.post("", response_model=CameraResponse, dependencies=[Depends(security)])
def create_camera(camera: CameraCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Criar uma nova câmera"""
    # Check if camera name already exists
    existing_camera = db.query(Camera).filter(Camera.name == camera.name).first()
    if existing_camera:
        raise HTTPException(status_code=400, detail="Camera with this name already exists")
    
    # Validate alert types
    if camera.enabled_alerts:
        valid_alerts = db.query(AlertType).filter(AlertType.code.in_(camera.enabled_alerts)).all()
        if len(valid_alerts) != len(camera.enabled_alerts):
            raise HTTPException(status_code=400, detail="Some alert types are invalid")
    
    new_camera = Camera(
        name=camera.name,
        ip_address=camera.ip_address,
        port=camera.port,
        enabled_alerts=camera.enabled_alerts,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_camera)
    db.commit()
    db.refresh(new_camera)
    
    return CameraResponse(
        id=new_camera.id,
        name=new_camera.name,
        ip_address=new_camera.ip_address,
        port=new_camera.port,
        enabled_alerts=new_camera.enabled_alerts or [],
        is_active=new_camera.is_active,
        created_at=new_camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=new_camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )


@router.get("/{camera_id}", response_model=CameraResponse, dependencies=[Depends(security)])
def get_camera(camera_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Obter uma câmera específica"""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        ip_address=camera.ip_address,
        port=camera.port,
        enabled_alerts=camera.enabled_alerts or [],
        is_active=camera.is_active,
        created_at=camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )


@router.put("/{camera_id}", response_model=CameraResponse, dependencies=[Depends(security)])
def update_camera(camera_id: int, camera_update: CameraUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Atualizar uma câmera"""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Check for name conflicts if name is being updated
    if camera_update.name and camera_update.name != camera.name:
        existing_camera = db.query(Camera).filter(Camera.name == camera_update.name).first()
        if existing_camera:
            raise HTTPException(status_code=400, detail="Camera with this name already exists")
    
    # Validate alert types if being updated
    if camera_update.enabled_alerts is not None:
        valid_alerts = db.query(AlertType).filter(AlertType.code.in_(camera_update.enabled_alerts)).all()
        if len(valid_alerts) != len(camera_update.enabled_alerts):
            raise HTTPException(status_code=400, detail="Some alert types are invalid")
    
    # Update camera fields
    update_data = camera_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)
    
    camera.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(camera)
    
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        ip_address=camera.ip_address,
        port=camera.port,
        enabled_alerts=camera.enabled_alerts or [],
        is_active=camera.is_active,
        created_at=camera.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=camera.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )


@router.delete("/{camera_id}", dependencies=[Depends(security)])
def delete_camera(camera_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Deletar uma câmera"""
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    db.delete(camera)
    db.commit()
    return {"message": "Camera deleted successfully"} 