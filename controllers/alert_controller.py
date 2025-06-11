"""
Controller de gerenciamento de alertas
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional

from config.security import security, get_current_user
from config.database_config import get_database
from models import AlertType, CameraAlert, Camera, User
from schemas import (AlertTypeCreate, AlertTypeResponse, AlertTypeListResponse,
                    CameraAlertCreate, CameraAlertResponse, CameraAlertListResponse)

router = APIRouter(prefix="/alerts")


@router.get("/types", response_model=AlertTypeListResponse, dependencies=[Depends(security)])
def get_alert_types(current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Obter todos os tipos de alerta"""
    alert_types = db.query(AlertType).all()
    
    type_responses = [
        AlertTypeResponse(
            id=alert_type.id,
            code=alert_type.code,
            name=alert_type.name,
            description=alert_type.description or "",
            icon=alert_type.icon,
            color=alert_type.color,
            severity=alert_type.severity,
            is_active=alert_type.is_active,
            created_at=alert_type.created_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert_type.created_at else "",
            updated_at=alert_type.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert_type.updated_at else ""
        ) for alert_type in alert_types
    ]
    
    return AlertTypeListResponse(alert_types=type_responses, total_count=len(type_responses))


@router.post("/types", response_model=AlertTypeResponse, dependencies=[Depends(security)])
def create_alert_type(alert_type: AlertTypeCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Criar um novo tipo de alerta"""
    # Check if code already exists
    existing_type = db.query(AlertType).filter(AlertType.code == alert_type.code).first()
    if existing_type:
        raise HTTPException(status_code=400, detail="Alert type with this code already exists")
    
    new_alert_type = AlertType(
        code=alert_type.code,
        name=alert_type.name,
        description=alert_type.description,
        icon=alert_type.icon,
        color=alert_type.color,
        severity=alert_type.severity,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_alert_type)
    db.commit()
    db.refresh(new_alert_type)
    
    return AlertTypeResponse(
        id=new_alert_type.id,
        code=new_alert_type.code,
        name=new_alert_type.name,
        description=new_alert_type.description or "",
        icon=new_alert_type.icon,
        color=new_alert_type.color,
        severity=new_alert_type.severity,
        is_active=new_alert_type.is_active,
        created_at=new_alert_type.created_at.strftime("%Y-%m-%d %H:%M:%S GMT"),
        updated_at=new_alert_type.updated_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )


@router.post("/cameras", response_model=CameraAlertResponse, dependencies=[Depends(security)])
def create_camera_alert(alert: CameraAlertCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Criar um alerta de câmera"""
    # Validate camera exists
    camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Validate alert type exists
    alert_type = db.query(AlertType).filter(AlertType.id == alert.alert_type_id).first()
    if not alert_type:
        raise HTTPException(status_code=404, detail="Alert type not found")
    
    new_alert = CameraAlert(
        camera_id=alert.camera_id,
        alert_type_id=alert.alert_type_id,
        alert_metadata=alert.alert_metadata,    
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    
    return CameraAlertResponse(
        id=new_alert.id,
        camera_id=new_alert.camera_id,
        camera_name=camera.name,
        alert_type_id=alert_type.id,
        alert_type_code=alert_type.code,
        alert_type_name=alert_type.name,
        alert_metadata=new_alert.alert_metadata,
        resolved=new_alert.resolved,
        severity=alert_type.severity,
        triggered_at=new_alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S GMT") if new_alert.triggered_at else None,
        resolved_at=new_alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if new_alert.resolved_at else None,
        resolved_by=new_alert.resolved_by
    )


@router.get("/cameras", response_model=CameraAlertListResponse, dependencies=[Depends(security)])
def get_camera_alerts(
    camera_id: Optional[int] = None,
    alert_type_code: Optional[str] = None,
    resolved: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Obter alertas de câmera com filtros opcionais"""
    query = db.query(CameraAlert)
    
    if camera_id:
        query = query.filter(CameraAlert.camera_id == camera_id)
    if alert_type_code:
        alert_type = db.query(AlertType).filter(AlertType.code == alert_type_code).first()
        query = query.filter(CameraAlert.alert_type_id == alert_type.id)
    if resolved is not None:
        query = query.filter(CameraAlert.resolved == resolved)
    
    alerts = query.order_by(CameraAlert.triggered_at.desc()).all()
    
    alert_responses = []
    for alert in alerts:
        camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
        alert_type = db.query(AlertType).filter(AlertType.id == alert.alert_type_id).first()
        
        alert_responses.append(CameraAlertResponse(
            id=alert.id,
            camera_id=alert.camera_id,
            camera_name=camera.name if camera else "Unknown",
            alert_type_id=alert_type.id if alert_type else None,
            alert_type_code=alert_type.code if alert_type else None,
            alert_type_name=alert_type.name if alert_type else "Unknown",
            alert_metadata=alert.alert_metadata,
            resolved=alert.resolved,
            triggered_at=alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.triggered_at else None,
            resolved_at=alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.resolved_at else None,
            resolved_by=alert.resolved_by,
            severity=alert_type.severity
        ))
    
    return CameraAlertListResponse(alerts=alert_responses, total_count=len(alert_responses))


@router.put("/cameras/{alert_id}/resolve", response_model=CameraAlertResponse, dependencies=[Depends(security)])
def resolve_camera_alert(alert_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_database)):
    """Resolver um alerta de câmera"""
    alert = db.query(CameraAlert).filter(CameraAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if alert.resolved:
        raise HTTPException(status_code=400, detail="Alert is already resolved")
    
    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = current_user.username
    
    db.commit()
    db.refresh(alert)
    
    camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    alert_type = db.query(AlertType).filter(AlertType.id == alert.alert_type_id).first()
    
    return CameraAlertResponse(
        id=alert.id,
        camera_id=alert.camera_id,
        camera_name=camera.name if camera else "Unknown",
        alert_type_id=alert_type.id if alert_type else None,
        alert_type_code=alert_type.code if alert_type else None,
        alert_type_name=alert_type.name if alert_type else "Unknown",
        alert_metadata=alert.alert_metadata,
        resolved=alert.resolved,
        triggered_at=alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.triggered_at else None,
        resolved_at=alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.resolved_at else None,
        resolved_by=alert.resolved_by,
        severity=alert_type.severity
    ) 