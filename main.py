"""
Aplicação principal refatorada com estrutura modular
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

logger = logging.getLogger(__name__)

# Flag para controlar se o sistema básico está pronto
_system_ready = False
# Flag para controlar se o background completo está pronto
_background_ready = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação"""
    global _system_ready, _background_ready
    
    # Startup - Inicializar sistemas críticos RAPIDAMENTE
    try:
        logger.info("🚀 Iniciando DIGEF-X Power Management API v2.0...")
        
        # 1. Criar tabelas do banco de dados (rápido)
        create_tables()
        logger.info("✅ Banco de dados inicializado")
        
        # 2. Inicializar Background Manager (não-bloqueante)
        logger.info("⚡ Inicializando sistema de background (não-bloqueante)...")
        await background_manager.startup()  # Agora retorna imediatamente
        logger.info("✅ Background Manager startup concluído")
        
        # 3. Sistema básico está pronto (API pode receber requisições)
        _system_ready = True
        logger.info("🎉 DIGEF-X Power Management API v2.0 PRONTA para receber requisições!")
        
        # 4. Monitorar inicialização do background em separado
        asyncio.create_task(_monitor_background_initialization())
        
    except Exception as e:
        logger.error(f"❌ ERRO CRÍTICO durante startup: {e}")
        # Mesmo com erro, permitir que a API funcione (para debug)
        _system_ready = True
        logger.warning("⚠️  API disponível com funcionalidade limitada devido a erro na inicialização")
    
    yield
    
    # Shutdown
    try:
        logger.info("🛑 Finalizando DIGEF-X Power Management API...")
        _system_ready = False
        _background_ready = False
        
        # Finalizar Background Manager
        await background_manager.shutdown()
        logger.info("✅ Background Manager finalizado")
        
        logger.info("👋 API finalizada com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ Erro durante shutdown: {e}")

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

# Inicialização da aplicação
app = FastAPI(
    title="DIGEF-X Power Management API",
    description="API para monitoramento de energia e gerenciamento de dispositivos",
    version="2.0.0",
    swagger_ui_parameters={
        "persistAuthorization": True,
    },
    lifespan=lifespan
)

# Middleware para verificar status do sistema (mais permissivo)
@app.middleware("http")
async def check_system_ready(request, call_next):
    """Middleware que verifica se o sistema básico está pronto"""
    # Endpoints sempre disponíveis (mesmo durante inicialização)
    always_available = ["/", "/health", "/docs", "/openapi.json", "/redoc"]
    
    # Endpoints de background sempre disponíveis (para monitoramento)
    background_endpoints = ["/background/status", "/background/health"]
    
    # Endpoints básicos (não dependem do background completo)
    basic_endpoints = ["/api/v1/auth", "/api/v1/devices", "/api/v1/cameras"]
    
    # Permitir endpoints básicos mesmo se background não estiver 100% pronto
    if any(request.url.path.startswith(path) for path in always_available + background_endpoints + basic_endpoints):
        return await call_next(request)
    
    # Para endpoints avançados, verificar se sistema básico está pronto
    if not _system_ready:
        raise HTTPException(
            status_code=503, 
            detail="Sistema ainda inicializando. Aguarde alguns segundos e tente novamente."
        )
    
    # Endpoints que dependem especificamente do background completo
    background_dependent = ["/api/v1/alerts"]
    
    if any(request.url.path.startswith(path) for path in background_dependent):
        if not _background_ready:
            raise HTTPException(
                status_code=503,
                detail="Sistema de alertas ainda inicializando. Aguarde e tente novamente."
            )
    
    return await call_next(request)

# Configuração de segurança para Swagger
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
    if app.openapi_schema:
        return app.openapi_schema
    
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


app.openapi = custom_openapi


@app.get("/")
async def root():
    """Endpoint raiz da API"""
    return {
        "message": "DIGEF-X Power Management API v2.0",
        "status": "ready" if _system_ready else "initializing",
        "system_ready": _system_ready,
        "background_ready": _background_ready,
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
