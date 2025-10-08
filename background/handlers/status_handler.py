import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict

from models import SessionLocal, Camera, CameraStatus
from services.network_service import is_connected
from ..serial_manager import get_serial_manager

logger = logging.getLogger(__name__)

class StatusHandler:
    """Handler para monitoramento e envio de status para ESP32"""
    
    def __init__(self):
        self.is_initialized = False
        # Usar conexão serial compartilhada (não criar própria)
        
        # Configurações de monitoramento
        self.status_interval = 5  # Enviar status a cada 5 segundos
        self.heartbeat_interval = 3  # Heartbeat a cada 3 segundos
        
        # Estado atual do sistema
        self.current_status = {
            'pc_online': True,
            'internet_online': False,
            'camera_1': False,
            'camera_2': False,
            'camera_3': False,
            'camera_4': False,
            'application_running': True
        }
        
        # Task de monitoramento
        self._monitoring_task = None
        self._heartbeat_task = None
        
    async def initialize(self):
        """Inicializa o handler de status usando SerialManager"""
        try:
            logger.info("🚀 Inicializando Status Handler...")
            
            # Obter SerialManager
            manager = get_serial_manager()
            
            # Garantir que SerialManager está rodando
            if not manager.is_running():
                logger.info("Iniciando SerialManager...")
                manager.start()
                await asyncio.sleep(0.5)  # Aguardar inicialização
            
            # Enviar comando inicial de sincronização
            success = await self._send_command_async("INIT:OK", wait_for_ack=True)
            if success:
                logger.info("📡 Comando INIT enviado com sucesso")
            else:
                logger.warning("⚠️ Falha ao enviar comando INIT")
            
            # Iniciar tarefas de monitoramento
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            self.is_initialized = True
            logger.info("✅ Status Handler inicializado")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Status Handler: {e}")
            raise
    
    async def _monitoring_loop(self):
        """Loop principal de monitoramento de status"""
        logger.info("🔄 Iniciando loop de monitoramento de status...")
        
        while self.is_initialized:
            try:
                # Coletar status atual do sistema
                status = await self._collect_system_status()
                
                # Verificar se houve mudanças
                if self._status_changed(status):
                    logger.info(f"📊 Status atualizado: {status}")
                    self.current_status = status
                    
                    # Enviar status para ESP32
                    await self._send_status_to_esp(status)
                
                # Aguardar próximo ciclo
                await asyncio.sleep(self.status_interval)
                
            except Exception as e:
                logger.error(f"❌ Erro no loop de monitoramento: {e}")
                await asyncio.sleep(self.status_interval)
    
    async def _heartbeat_loop(self):
        """Loop de heartbeat robusto para indicar que aplicação está rodando"""
        logger.info("💓 Iniciando heartbeat para ESP32...")
        
        heartbeat_failures = 0
        max_failures = 3
        
        while self.is_initialized:
            try:
                # Enviar heartbeat
                await self._send_heartbeat()
                heartbeat_failures = 0  # Reset contador de falhas
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                heartbeat_failures += 1
                logger.error(f"❌ Erro no heartbeat ({heartbeat_failures}/{max_failures}): {e}")
                
                if heartbeat_failures >= max_failures:
                    logger.error("🚨 Muitas falhas de heartbeat consecutivas!")
                    # O SerialManager cuidará da reconexão automaticamente
                    heartbeat_failures = 0
                
                await asyncio.sleep(self.heartbeat_interval)
    
    async def _collect_system_status(self) -> Dict[str, bool]:
        """Coleta status atual do sistema"""
        try:
            db = SessionLocal()
            
            # 1. Status da internet
            internet_online = is_connected("8.8.8.8", 53, timeout=3)
            
            # 2. Status das câmeras (últimos 30 segundos)
            cutoff_time = datetime.utcnow() - timedelta(seconds=30)
            
            camera_status = {}
            for camera_num in range(1, 5):  # Câmeras 1-4
                camera = db.query(Camera).filter(Camera.name == f'camera_{camera_num}').first()
                
                if camera and camera.is_active:
                    # Verificar último status da câmera
                    latest_status = db.query(CameraStatus).filter(
                        CameraStatus.camera_id == camera.id,
                        CameraStatus.timestamp >= cutoff_time
                    ).order_by(CameraStatus.timestamp.desc()).first()
                    
                    camera_status[f'camera_{camera_num}'] = (
                        latest_status is not None and latest_status.is_connected
                    )
                else:
                    camera_status[f'camera_{camera_num}'] = False
            
            # 3. Status do PC (sempre True se chegou até aqui)
            pc_online = True
            
            # 4. Status da aplicação (sempre True se chegou até aqui)
            application_running = True
            
            db.close()
            
            return {
                'pc_online': pc_online,
                'internet_online': internet_online,
                'application_running': application_running,
                **camera_status
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao coletar status: {e}")
            return self.current_status  # Retornar último status conhecido
    
    def _status_changed(self, new_status: Dict[str, bool]) -> bool:
        """Verifica se o status mudou"""
        return new_status != self.current_status
    
    async def _send_command_async(self, command: str, wait_for_ack: bool = False) -> bool:
        """
        Envia comando via SerialManager de forma assíncrona
        
        Args:
            command: Comando a ser enviado
            wait_for_ack: Se deve aguardar ACK
            
        Returns:
            True se comando foi enviado com sucesso
        """
        try:
            manager = get_serial_manager()
            
            # Executar em thread pool para não bloquear o event loop
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                manager.send_command_sync,
                command,
                wait_for_ack,
                2.0  # timeout
            )
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar comando: {e}")
            return False
    
    async def _send_status_to_esp(self, status: Dict[str, bool]):
        """Envia status completo para ESP32"""
        try:
            # Formato: STATUS:PC:1,INTERNET:1,APP:1,CAM1:1,CAM2:0,CAM3:1,CAM4:0
            status_parts = []
            status_parts.append(f"PC:{1 if status['pc_online'] else 0}")
            status_parts.append(f"INTERNET:{1 if status['internet_online'] else 0}")
            status_parts.append(f"APP:{1 if status['application_running'] else 0}")
            
            for i in range(1, 5):
                cam_status = 1 if status.get(f'camera_{i}', False) else 0
                status_parts.append(f"CAM{i}:{cam_status}")
            
            command = "STATUS:" + ",".join(status_parts)
            
            success = await self._send_command_async(command, wait_for_ack=True)
            
            if success:
                logger.debug(f"📡 Status enviado para ESP32: {command}")
            else:
                logger.warning("⚠️ Falha ao enviar status para ESP32")
                
        except Exception as e:
            logger.error(f"❌ Erro ao enviar status: {e}")
    
    async def _send_heartbeat(self):
        """Envia heartbeat para ESP32 com verificação de ACK"""
        try:
            timestamp = int(time.time())
            command = f"HEARTBEAT:{timestamp}"
            
            success = await self._send_command_async(command, wait_for_ack=True)
            
            if success:
                logger.debug(f"💓 Heartbeat OK: {timestamp} (ACK recebido)")
            else:
                logger.warning(f"⚠️ Heartbeat FALHOU: {timestamp} (sem ACK do ESP32)")
                
        except Exception as e:
            logger.error(f"❌ Erro crítico no heartbeat: {e}")
    
    
    async def handle_event(self, event) -> bool:
        """Handler para eventos (se necessário integrar com EventBus)"""
        # Este handler funciona de forma autônoma
        return True
    
    async def cleanup(self):
        """Finaliza o handler de status"""
        try:
            logger.info("🛑 Finalizando Status Handler...")
            
            self.is_initialized = False
            
            # Cancelar tarefas
            if self._monitoring_task:
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            # Enviar comando de desligamento para ESP32
            await self._send_command_async("SHUTDOWN:1", wait_for_ack=True)
            
            logger.info("✅ Status Handler finalizado")
            
        except Exception as e:
            logger.error(f"❌ Erro ao finalizar Status Handler: {e}")
    
    def get_current_status(self) -> Dict[str, bool]:
        """Retorna status atual do sistema"""
        return self.current_status.copy()
    
    def force_status_update(self):
        """Força atualização imediata do status"""
        # Será implementado se necessário para triggers externos