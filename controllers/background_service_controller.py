"""
Controller para gerenciamento do serviço de background
Endpoints simplificados para monitoramento e controle opcional
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from background.background_manager import background_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/background/status")
async def get_background_status():
    """
    Status atual do sistema de background
    Sempre disponível para monitoramento
    """
    try:
        return background_manager.get_status()
    except Exception as e:
        logger.error(f"Erro ao obter status do background: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/background/restart")
async def restart_background_service(background_tasks: BackgroundTasks):
    """
    Reiniciar o serviço de background
    Útil para aplicar novas configurações
    """
    try:
        if not background_manager.is_ready:
            raise HTTPException(status_code=400, detail="Background manager não está pronto")
        
        # Executar restart em background para não bloquear a resposta
        background_tasks.add_task(_restart_background)
        
        return {
            "message": "Restart do background service iniciado",
            "status": "restarting"
        }
    except Exception as e:
        logger.error(f"Erro ao reiniciar background service: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/background/stop")
async def stop_background_service():
    """
    Parar o serviço de background manualmente
    Para manutenção ou debug
    """
    try:
        if not background_manager.is_ready:
            raise HTTPException(status_code=400, detail="Background manager não está pronto")
        
        if not background_manager.is_running:
            return {
                "message": "Background service já está parado",
                "status": "stopped"
            }
        
        await background_manager.stop()
        
        return {
            "message": "Background service parado com sucesso",
            "status": "stopped"
        }
    except Exception as e:
        logger.error(f"Erro ao parar background service: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/background/start")
async def start_background_service():
    """
    Iniciar o serviço de background manualmente
    Útil após parada manual
    """
    try:
        if not background_manager.is_ready:
            raise HTTPException(status_code=400, detail="Background manager não está pronto")
        
        if background_manager.is_running:
            return {
                "message": "Background service já está rodando",
                "status": "running"
            }
        
        await background_manager.start()
        
        return {
            "message": "Background service iniciado com sucesso",
            "status": "running"
        }
    except Exception as e:
        logger.error(f"Erro ao iniciar background service: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/background/health")
async def background_health_check():
    """
    Health check específico para o background service
    Útil para monitoramento externo
    """
    try:
        status = background_manager.get_status()
        
        # Determinar health baseado no status
        is_healthy = status.get("status") in ["running", "stopped"]
        
        return {
            "healthy": is_healthy,
            "status": status.get("status", "unknown"),
            "message": status.get("message", "OK"),
            "timestamp": status.get("last_check")
        }
    except Exception as e:
        logger.error(f"Erro no health check: {e}")
        return {
            "healthy": False,
            "status": "error",
            "message": str(e)
        }

async def _restart_background():
    """Função auxiliar para restart em background"""
    try:
        await background_manager.restart()
        logger.info("Background service reiniciado com sucesso")
    except Exception as e:
        logger.error(f"Erro durante restart do background service: {e}") 