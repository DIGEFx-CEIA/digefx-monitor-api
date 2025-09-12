"""
Background Manager - Gerenciamento global do sistema de background
"""

import logging
from typing import Optional
from .event_handler_manager import EventHandlerManager
from .event_system import EventBus
from config import app_config
from .host_monitor import start_host_monitoring
from .serial_monitor import start_serial_monitoring
from .camera_monitor import start_camera_monitoring
from .file_processor import process_new_video
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio

logger = logging.getLogger(__name__)


class VideoFileHandler(FileSystemEventHandler):
    """Handler para monitorar novos arquivos de vídeo"""    

    def __init__(self, controller):
        self.logger = logging.getLogger(__name__)
        self.controller = controller
        self.loop = None

    def set_event_loop(self, loop):
        """Define o loop de eventos para executar tarefas assíncronas"""
        self.loop = loop

    def on_created(self, event):
        """Chamado quando um novo arquivo é criado"""
        if not event.is_directory:
            file_path = event.src_path
            if file_path.endswith('.mp4'):
                self.logger.info(f"Novo arquivo detectado: {file_path}")
                self._schedule_async_processing(file_path)

    def _schedule_async_processing(self, file_path: str):
        """Agenda o processamento assíncrono do arquivo de vídeo"""
        try:
            if self.loop and not self.loop.is_closed():
                # Executar a corrotina no loop de eventos principal de forma thread-safe
                future = asyncio.run_coroutine_threadsafe(
                    process_new_video(file_path), 
                    self.loop
                )
                # Opcional: adicionar callback para capturar erros
                future.add_done_callback(self._handle_processing_result)
            else:
                self.logger.error("Loop de eventos não disponível para processar arquivo")
        except Exception as e:
            self.logger.error(f"Erro ao agendar processamento do arquivo {file_path}: {e}")

    def _handle_processing_result(self, future):
        """Callback para lidar com o resultado do processamento"""
        try:
            result = future.result()  # Isso irá levantar qualquer exceção que ocorreu
            self.logger.debug("Processamento de arquivo concluído com sucesso")
        except Exception as e:
            self.logger.error(f"Erro durante processamento assíncrono: {e}")

class BackgroundManager:
    """Gerenciador global do sistema de background"""
    
    def __init__(self):
        self.handler_manager: Optional[EventHandlerManager] = None
        self._is_running = False
        self._startup_completed = False
        self._monitors_started = False
        self._initialization_task = None
        app_config.ensure_directories()  # Garantir que os diretórios existem

    async def startup(self):
        """Inicialização não-bloqueante do sistema de background"""
        try:
            logger.info("🚀 Iniciando Background Manager (modo não-bloqueante)...")
            
            # 1. Iniciar monitores básicos imediatamente (síncronos)
            self._start_basic_monitors()
            self._start_file_monitoring()
            # 2. Iniciar inicialização completa em background
            self._initialization_task = asyncio.create_task(self._initialize_background_systems())
            
            # 3. Retornar imediatamente - não aguardar a inicialização completa
            logger.info("✅ Background Manager startup iniciado - sistemas inicializando em background...")
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar Background Manager: {e}")
            self._startup_completed = True  # Marcar como completo mesmo com erro
            raise
    
    async def _initialize_background_systems(self):
        """Inicialização completa dos sistemas de background (executado em background)"""
        try:
            logger.info("🔄 Inicializando sistemas de background...")
            
            # 1. Criar e inicializar o gerenciador de handlers
            self.handler_manager = EventHandlerManager()
            await self.handler_manager.initialize()
            logger.info("✅ EventHandlerManager inicializado")
            
            # 2. Sistema simplificado - handlers já inicializados e registrados no EventBus
            # Não precisa de processamento adicional - tudo é baseado em eventos
            
            # 3. Marcar como inicializado
            self._startup_completed = True
            logger.info("🎉 Todos os sistemas de background inicializados com sucesso!")
            
        except Exception as e:
            logger.error(f"❌ Erro durante inicialização dos sistemas de background: {e}")
            self._startup_completed = True  # Marcar como completo mesmo com erro
    
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

    def _start_file_monitoring(self):
        # Configurar observador para novos arquivos
        event_handler = VideoFileHandler(self)
        
        # Passar o loop de eventos atual para o handler
        try:
            current_loop = asyncio.get_running_loop()
            event_handler.set_event_loop(current_loop)
            logger.info("Loop de eventos configurado para o VideoFileHandler")
        except RuntimeError:
            # Se não há loop rodando, tentar obter o loop padrão
            try:
                current_loop = asyncio.get_event_loop()
                event_handler.set_event_loop(current_loop)
                logger.warning("Usando loop de eventos padrão para VideoFileHandler")
            except Exception as e:
                logger.error(f"Não foi possível configurar loop de eventos: {e}")
        
        self.observer = Observer()
        self.observer.schedule(event_handler, str(app_config.VIDEO_DIR), recursive=True)
        # Iniciar monitoramento
        self.observer.start()
        logger.info(f"Monitoramento iniciado na pasta {app_config.VIDEO_DIR}. Aguardando novos arquivos...")
    
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
            
            # Parar o observer de arquivos
            if hasattr(self, 'observer') and self.observer:
                self.observer.stop()
                self.observer.join()
                logger.info("✅ File Observer finalizado")
            
            # Cancelar task de inicialização se ainda estiver rodando
            if self._initialization_task and not self._initialization_task.done():
                self._initialization_task.cancel()
                try:
                    await self._initialization_task
                except asyncio.CancelledError:
                    logger.info("Task de inicialização cancelada")
            
            # Finalizar EventHandlerManager
            if self.handler_manager:
                await self.handler_manager.cleanup()
                logger.info("✅ EventHandlerManager finalizado")
            
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
        logger.info("▶️ Sistema baseado em eventos - sempre ativo após inicialização")
        # Sistema simplificado não precisa start/stop manual
        # Os handlers ficam sempre ativos escutando eventos
    
    async def stop(self):
        """Parar manualmente o sistema"""
        logger.info("⏹️ Sistema baseado em eventos - use shutdown() para finalizar completamente")
        # Sistema simplificado não precisa start/stop manual
    
    def get_status(self) -> dict:
        """Status atual do sistema"""
        if not self._startup_completed:
            initialization_status = "starting"
            if self._initialization_task:
                if self._initialization_task.done():
                    initialization_status = "completed" if not self._initialization_task.exception() else "failed"
                else:
                    initialization_status = "initializing"
            
            return {
                "status": initialization_status,
                "message": "Sistema inicializando em background..." if initialization_status == "initializing" else "Sistema iniciando..."
            }
        
        if not self.handler_manager:
            return {
                "status": "error",
                "message": "EventHandlerManager não inicializado"
            }
        
        try:
            # Status do gerenciador de handlers
            handler_stats = self.handler_manager.get_stats() if self.handler_manager else {}
            
            # Status geral do sistema
            system_status = {
                "status": "running",  # Background Manager está sempre running após startup
                "startup_completed": self._startup_completed,
                "basic_monitors": {
                    "host_monitor": self._monitors_started,
                    "serial_monitor": self._monitors_started,
                    "camera_monitor": self._monitors_started,
                    "status": "running" if self._monitors_started else "stopped"
                },
                "event_handlers": {
                    "status": "running" if handler_stats.get("is_initialized") else "stopped",
                    **handler_stats
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
        return self._startup_completed and self.handler_manager is not None and self.handler_manager.is_ready()
    
    @property
    def monitors_running(self) -> bool:
        return self._monitors_started


# Instância global
background_manager = BackgroundManager() 