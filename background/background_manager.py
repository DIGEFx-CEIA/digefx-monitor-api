"""
Background Manager - Gerenciamento global do sistema de background
"""

import logging
from typing import Optional
from .camera_alert_processor import CameraAlertProcessor
from .event_system import EventBus
from .host_monitor import start_host_monitoring
from .serial_monitor import start_serial_monitoring
from .camera_monitor import start_camera_monitoring
import asyncio

logger = logging.getLogger(__name__)

class BackgroundManager:
    """Gerenciador global do sistema de background"""
    
    def __init__(self):
        self.processor: Optional[CameraAlertProcessor] = None
        self._is_running = False
        self._startup_completed = False
        self._monitors_started = False
    
    async def startup(self):
        """Inicialização automática do sistema de background"""
        try:
            logger.info("🚀 Iniciando Background Manager...")
            
            # 1. Iniciar monitores básicos existentes (sempre executam)
            self._start_basic_monitors()
            
            # 2. Iniciar sistema de processamento de alertas
            self.processor = CameraAlertProcessor()
            
            # 3. Inicializar processador (sem bloquear)
            await self.processor.initialize()
            
            # 4. Iniciar processamento em background (não bloquear)
            asyncio.create_task(self._start_alert_processing())
            
            self._startup_completed = True
            logger.info("✅ Background Manager iniciado com sucesso!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar Background Manager: {e}")
            self._startup_completed = True  # Marcar como completo mesmo com erro
            raise
    
    def _start_basic_monitors(self):
        """Inicia os monitores básicos (host, serial, camera)"""
        try:
            logger.info("📊 Iniciando monitores básicos...")
            
            # Monitor do Host (CPU, RAM, Disk, Temperature)
            start_host_monitoring()
            logger.info("✅ Host Monitor iniciado")
            
            # Monitor Serial (Comunicação ESP32)
            start_serial_monitoring()  
            logger.info("✅ Serial Monitor iniciado")
            
            # Monitor de Câmeras (Conectividade)
            start_camera_monitoring()
            logger.info("✅ Camera Monitor iniciado")
            
            self._monitors_started = True
            logger.info("🎯 Todos os monitores básicos iniciados!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar monitores básicos: {e}")
            # Continuar mesmo com erro nos monitores
    
    async def _start_alert_processing(self):
        """Inicia o processamento de alertas em background"""
        try:
            logger.info("🔄 Iniciando processamento de alertas em background...")
            await self.processor.start_processing()
            self._is_running = True
            logger.info("✅ Processamento de alertas iniciado")
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar processamento de alertas: {e}")
            self._is_running = False
    
    async def shutdown(self):
        """Finalização graceful do sistema"""
        try:
            logger.info("🛑 Finalizando Background Manager...")
            
            # Parar processamento de alertas
            if self.processor and self._is_running:
                await self.processor.stop_processing()
                self._is_running = False
                logger.info("✅ Alert Processor finalizado")
            
            # Nota: Os monitores básicos continuam rodando (threads daemon)
            # Eles serão finalizados automaticamente quando a aplicação parar
            
            logger.info("✅ Background Manager finalizado!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao finalizar Background Manager: {e}")
    
    async def restart(self):
        """Reiniciar o sistema de background"""
        if self._is_running:
            await self.stop()
        await self.start()
    
    async def start(self):
        """Iniciar manualmente o sistema"""
        if not self._is_running and self.processor:
            await self.processor.start_processing()
            self._is_running = True
            logger.info("▶️ Background processing iniciado manualmente")
    
    async def stop(self):
        """Parar manualmente o sistema"""
        if self._is_running and self.processor:
            await self.processor.stop_processing()
            self._is_running = False
            logger.info("⏹️ Background processing parado manualmente")
    
    def get_status(self) -> dict:
        """Status atual do sistema"""
        if not self._startup_completed:
            return {
                "status": "starting",
                "message": "Sistema iniciando..."
            }
        
        if not self.processor:
            return {
                "status": "error",
                "message": "Processor não inicializado"
            }
        
        try:
            # Status do processamento de alertas
            stats = self.processor.get_stats() if self.processor else {}
            
            # Determinar status do processamento de alertas
            alert_processing_status = "running" if self._is_running else "starting"
            if not self._is_running and self._startup_completed:
                # Se startup completou mas não está rodando, pode estar iniciando ainda
                alert_processing_status = "initializing"
            
            # Status geral do sistema
            system_status = {
                "status": "running",  # Background Manager está sempre running após startup
                "is_running": self._is_running,
                "startup_completed": self._startup_completed,
                "basic_monitors": {
                    "host_monitor": self._monitors_started,
                    "serial_monitor": self._monitors_started,
                    "camera_monitor": self._monitors_started,
                    "status": "running" if self._monitors_started else "stopped"
                },
                "alert_processing": {
                    "status": alert_processing_status,
                    **stats
                }
            }
            
            return system_status
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erro ao obter status: {str(e)}"
            }
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def is_ready(self) -> bool:
        return self._startup_completed and self.processor is not None
    
    @property
    def monitors_running(self) -> bool:
        return self._monitors_started

# Instância global
background_manager = BackgroundManager() 