"""
Aplicação principal refatorada com estrutura modular
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.app_config import app_config
from config.database_config import create_tables
from controllers import setup_routes
from background import start_all_background_services


# Inicialização da aplicação
app = FastAPI(
    title="DIGEF-X Power Management API",
    description="API para monitoramento de energia e gerenciamento de dispositivos",
    version="2.0.0"
)

# Configuração CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Inicialização da aplicação"""
    # Criar tabelas do banco de dados
    create_tables()
    
    # Iniciar serviços de background
    start_all_background_services()
    
    print("✅ DIGEF-X Power Management API v2.0 iniciada com sucesso!")


@app.get("/")
async def root():
    """Endpoint raiz da API"""
    return {
        "message": "DIGEF-X Power Management API v2.0",
        "status": "running",
        "documentation": "/docs"
    }


@app.get("/health")
async def health_check():
    """Verificação de saúde da API"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "uptime": "ok"
    }


# Configuração das rotas
setup_routes(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_refactored:app",
        host="0.0.0.0",
        port=7000,
        reload=True,
        log_level="info"
    ) 