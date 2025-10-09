"""
Aplicação principal refatorada com estrutura modular e sistema de feature flags
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from config.app_config import app_config
from config.database_config import create_tables
from controllers import setup_routes
from background.background_manager import background_manager
import logging
import asyncio
import sys

logger = logging.getLogger(__name__)

# Flag para controlar se o sistema básico está pronto
_system_ready = False
# Flag para controlar se o background completo está pronto
_background_ready = False

async def initialize_system():
    """Inicialização do sistema baseada nas feature flags"""
    global _system_ready, _background_ready
    
    execution_mode = app_config.get_execution_mode()
    logger.info(f"🚀 Iniciando DIGEF-X Power Management System v2.0 (modo: {execution_mode})...")
    
    try:
        # 1. Inicializar banco de dados se necessário
        if app_config.should_enable_api() or app_config.should_enable_background_systems():
            create_tables()
            logger.info("✅ Banco de dados inicializado")
        
        # 2. Inicializar sistema de background
        if (app_config.should_enable_basic_monitors() or 
            app_config.should_enable_file_monitoring() or 
            app_config.should_enable_background_systems()):
            
            logger.info("⚡ Inicializando sistema de background...")
            await background_manager.startup() 
            logger.info("✅ Background Manager startup concluído")
            
            # Monitorar inicialização do background em separado
            asyncio.create_task(_monitor_background_initialization())
        else:
            logger.info("⏭️ Sistema de background desabilitado por feature flags")
            _background_ready = True
        
        # 3. Sistema básico está pronto
        _system_ready = True
        
        if app_config.should_enable_api():
            logger.info("🎉 DIGEF-X Power Management API v2.0 PRONTA para receber requisições!")
        else:
            logger.info("🎉 DIGEF-X Power Management System v2.0 PRONTO!")
        
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO durante startup: {e}")
        # Mesmo com erro, permitir que o sistema funcione (para debug)
        _system_ready = True
        _background_ready = True
        logger.warning("⚠️  Sistema disponível com funcionalidade limitada devido a erro na inicialização")

async def shutdown_system():
    """Finalização do sistema"""
    global _system_ready, _background_ready
    
    try:
        logger.info("🛑 Finalizando DIGEF-X Power Management System...")
        _system_ready = False
        _background_ready = False
        
        # Finalizar Background Manager se foi iniciado
        if (app_config.should_enable_basic_monitors() or 
            app_config.should_enable_file_monitoring() or 
            app_config.should_enable_background_systems()):
            
            await background_manager.shutdown()
            logger.info("✅ Background Manager finalizado")
        
        logger.info("👋 Sistema finalizado com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro durante shutdown: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação FastAPI"""
    await initialize_system()
    yield
    await shutdown_system()

async def _monitor_background_initialization():
    """Monitora a inicialização completa do background em separado"""
    global _background_ready
    
    try:
        # Aguardar até que o background esteja completamente inicializado
        max_wait_time = 120  # 2 minutos máximo
        wait_interval = 2    # Verificar a cada 2 segundos
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            if background_manager.is_ready:
                _background_ready = True
                logger.info("🎯 Background System completamente inicializado!")
                logger.info("🔄 Processamento de alertas de câmeras ativo")
                break
            
            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval
            
            if elapsed_time % 10 == 0:  # Log a cada 10 segundos
                logger.info(f"⏳ Aguardando inicialização completa do background... ({elapsed_time}s)")
        
        if not _background_ready:
            logger.warning("⚠️  Background system não foi completamente inicializado no tempo esperado")
            logger.warning("⚠️  API funcionará com funcionalidade limitada de alertas")
            
    except Exception as e:
        logger.error(f"❌ Erro ao monitorar inicialização do background: {e}")

# Inicialização da aplicação FastAPI (apenas se habilitada)
app = None
if app_config.should_enable_api():
    app = FastAPI(
        title="DIGEF-X Power Management API",
        description="API para monitoramento de energia e gerenciamento de dispositivos",
        version="2.0.0",
        swagger_ui_parameters={
            "persistAuthorization": True,
        },
        lifespan=lifespan
    )

# Configuração de segurança para Swagger e CORS (apenas se API habilitada)
if app:
    bearer_scheme = HTTPBearer()
    
    # Configuração CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def custom_openapi():
    """Configuração customizada do OpenAPI para incluir autenticação JWT"""
    if app and app.openapi_schema:
        return app.openapi_schema
    
    if not app:
        return None
    
    openapi_schema = get_openapi(
        title="DIGEF-X Power Management API",
        version="2.0.0",
        description="API para monitoramento de energia e gerenciamento de dispositivos",
        routes=app.routes,
    )
    
    # Configurar esquema de segurança
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Configurar OpenAPI apenas se API habilitada
if app:
    app.openapi = custom_openapi


# Endpoints da API (apenas se API habilitada)
if app:
    @app.get("/")
    async def root():
        """Endpoint raiz da API"""
        return {
            "message": "DIGEF-X Power Management API v2.0",
            "status": "ready" if _system_ready else "initializing",
            "system_ready": _system_ready,
            "background_ready": _background_ready,
            "execution_mode": app_config.get_execution_mode(),
            "documentation": "/docs"
        }

    @app.get("/health")
    async def health_check():
        """Verificação de saúde da API"""
        status = "healthy"
        if not _system_ready:
            status = "initializing"
        elif not _background_ready:
            status = "partially_ready"
        
        health_data = {
            "status": status,
            "version": "2.0.0",
            "execution_mode": app_config.get_execution_mode(),
            "system_ready": _system_ready,
            "background_ready": _background_ready,
            "uptime": "ok"
        }
        
        # Se background estiver pronto, incluir detalhes
        if _system_ready and background_manager.is_ready:
            try:
                bg_status = background_manager.get_status()
                health_data["background_status"] = bg_status
            except Exception as e:
                health_data["background_error"] = str(e)
        
        return health_data

    # Configuração das rotas
    setup_routes(app)

async def run_system_only():
    """Executa apenas o sistema de background sem FastAPI"""
    try:
        await initialize_system()
        
        # Manter o sistema rodando
        logger.info("🔄 Sistema rodando em modo background-only. Pressione Ctrl+C para parar.")
        
        # Aguardar indefinidamente
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("🛑 Interrupção recebida. Finalizando sistema...")
    except Exception as e:
        logger.error(f"❌ Erro durante execução do sistema: {e}")
    finally:
        await shutdown_system()

def main():
    """Função principal para execução do sistema"""
    execution_mode = app_config.get_execution_mode()
    
    if execution_mode in ["background_only", "monitors_only"]:
        # Executar apenas o sistema de background
        logger.info(f"🚀 Iniciando sistema em modo: {execution_mode}")
        asyncio.run(run_system_only())
    elif app_config.should_enable_api():
        # Executar com FastAPI (modo padrão)
        logger.info("🚀 Iniciando sistema com FastAPI")
        # O FastAPI será executado pelo uvicorn
        return app
    else:
        logger.error("❌ Configuração inválida: API desabilitada mas modo não é background_only ou monitors_only")
        sys.exit(1)

# Executar main se chamado diretamente
if __name__ == "__main__":
    main()
