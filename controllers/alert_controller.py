"""
Controller de gerenciamento de alertas
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from services.auth_service import get_current_user, get_db
from models import AlertType, CameraAlert, Camera, User
from schemas import (AlertTypeCreate, AlertTypeResponse, CameraAlertCreate, 
                    CameraAlertResponse, CameraAlertListResponse, AlertResolution)

router = APIRouter()


# Alert Types Management
@router.get("/alert-types", response_model=List[AlertTypeResponse])
def get_alert_types(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Obter todos os tipos de alerta disponíveis"""
    alert_types = db.query(AlertType).filter(AlertType.is_active == True).all()
    return [
        AlertTypeResponse(
            id=alert.id,
            code=alert.code,
            name=alert.name,
            description=alert.description,
            is_active=alert.is_active,
            created_at=alert.created_at.strftime("%Y-%m-%d %H:%M:%S GMT")
        ) for alert in alert_types
    ]


@router.post("/alert-types", response_model=AlertTypeResponse)
def create_alert_type(alert_type: AlertTypeCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Criar um novo tipo de alerta"""
    # Check if alert type already exists
    existing_alert = db.query(AlertType).filter(AlertType.code == alert_type.code).first()
    if existing_alert:
        raise HTTPException(status_code=400, detail="Alert type with this code already exists")
    
    new_alert = AlertType(
        code=alert_type.code,
        name=alert_type.name,
        description=alert_type.description,
        created_at=datetime.utcnow()
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    
    return AlertTypeResponse(
        id=new_alert.id,
        code=new_alert.code,
        name=new_alert.name,
        description=new_alert.description,
        is_active=new_alert.is_active,
        created_at=new_alert.created_at.strftime("%Y-%m-%d %H:%M:%S GMT")
    )


# Camera Alerts Management
@router.post("/camera-alerts", response_model=CameraAlertResponse)
def create_camera_alert(alert: CameraAlertCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Criar um novo alerta de câmera (tipicamente chamado pelo sistema de detecção de IA)"""
    # Validate camera exists
    camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Validate alert type exists
    alert_type = db.query(AlertType).filter(AlertType.code == alert.alert_type_code).first()
    if not alert_type:
        raise HTTPException(status_code=404, detail="Alert type not found")
    
    # Check if alert type is enabled for this camera
    if alert.alert_type_code not in (camera.enabled_alerts or []):
        raise HTTPException(status_code=400, detail="Alert type not enabled for this camera")
    
    new_alert = CameraAlert(
        camera_id=alert.camera_id,
        alert_type_code=alert.alert_type_code,
        detection_timestamp=datetime.utcnow(),
        confidence_score=alert.confidence_score,
        alert_metadata=alert.alert_metadata
    )
    db.add(new_alert)
    db.commit()
    db.refresh(new_alert)
    
    return CameraAlertResponse(
        id=new_alert.id,
        camera_id=new_alert.camera_id,
        camera_name=camera.name,
        alert_type_code=new_alert.alert_type_code,
        alert_type_name=alert_type.name,
        detection_timestamp=new_alert.detection_timestamp.strftime("%Y-%m-%d %H:%M:%S GMT"),
        confidence_score=new_alert.confidence_score,
        metadata=new_alert.alert_metadata,
        resolved=new_alert.resolved,
        resolved_at=new_alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if new_alert.resolved_at else None,
        resolved_by=new_alert.resolved_by
    )


@router.get("/camera-alerts", response_model=CameraAlertListResponse)
def get_camera_alerts(
    camera_id: int = None,
    alert_type: str = None,
    resolved: bool = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obter alertas de câmera com filtros opcionais"""
    query = db.query(CameraAlert)
    
    if camera_id:
        query = query.filter(CameraAlert.camera_id == camera_id)
    if alert_type:
        query = query.filter(CameraAlert.alert_type_code == alert_type)
    if resolved is not None:
        query = query.filter(CameraAlert.resolved == resolved)
    
    alerts = query.order_by(CameraAlert.detection_timestamp.desc()).limit(limit).all()
    
    alert_responses = []
    for alert in alerts:
        camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
        alert_type_obj = db.query(AlertType).filter(AlertType.code == alert.alert_type_code).first()
        
        alert_responses.append(CameraAlertResponse(
            id=alert.id,
            camera_id=alert.camera_id,
            camera_name=camera.name if camera else "Unknown",
            alert_type_code=alert.alert_type_code,
            alert_type_name=alert_type_obj.name if alert_type_obj else "Unknown",
            detection_timestamp=alert.detection_timestamp.strftime("%Y-%m-%d %H:%M:%S GMT"),
            confidence_score=alert.confidence_score,
            metadata=alert.alert_metadata,
            resolved=alert.resolved,
            resolved_at=alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.resolved_at else None,
            resolved_by=alert.resolved_by
        ))
    
    return CameraAlertListResponse(alerts=alert_responses, total_count=len(alert_responses))


@router.put("/camera-alerts/{alert_id}/resolve", response_model=CameraAlertResponse)
def resolve_camera_alert(alert_id: int, resolution: AlertResolution, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resolver ou desresolver um alerta de câmera"""
    alert = db.query(CameraAlert).filter(CameraAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.resolved = resolution.resolved
    if resolution.resolved:
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = current_user.id
    else:
        alert.resolved_at = None
        alert.resolved_by = None
    
    db.commit()
    db.refresh(alert)
    
    camera = db.query(Camera).filter(Camera.id == alert.camera_id).first()
    alert_type = db.query(AlertType).filter(AlertType.code == alert.alert_type_code).first()
    
    return CameraAlertResponse(
        id=alert.id,
        camera_id=alert.camera_id,
        camera_name=camera.name if camera else "Unknown",
        alert_type_code=alert.alert_type_code,
        alert_type_name=alert_type.name if alert_type else "Unknown",
        detection_timestamp=alert.detection_timestamp.strftime("%Y-%m-%d %H:%M:%S GMT"),
        confidence_score=alert.confidence_score,
        metadata=alert.alert_metadata,
        resolved=alert.resolved,
        resolved_at=alert.resolved_at.strftime("%Y-%m-%d %H:%M:%S GMT") if alert.resolved_at else None,
        resolved_by=alert.resolved_by
    ) 