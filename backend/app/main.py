from contextlib import asynccontextmanager
import asyncio
import logging
import httpx
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.supabase import get_supabase_client
from app.services.checkout_queue import get_checkout_queue


async def sync_loop():
    while True:
        try:
            await asyncio.to_thread(get_checkout_queue().drain)
        except Exception:
            logging.getLogger(__name__).exception('No se pudo ejecutar la sincronización local')
        await asyncio.sleep(max(1, settings.SYNC_INTERVAL_SECONDS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validar conexión con Supabase al arrancar
    try:
        supabase = get_supabase_client()
        # Prueba ligera
        res = supabase.table("productos").select("id").limit(1).execute()
        print(f"[STARTUP] Conexión con Supabase exitosa. ({len(res.data)} productos comprobados)")
    except Exception as e:
        print(f"[WARNING] No se pudo verificar Supabase al inicio: {e}")
    get_checkout_queue()
    task = asyncio.create_task(sync_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    print("[SHUTDOWN] Cerrando servicios de FastAPI POS Core.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="API Core para Sistema de Punto de Venta (POS) con Reconocimiento de Producto por Visión Computacional (YOLOv8 + pyzbar) y Base de Datos en Supabase.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)


@app.exception_handler(httpx.TransportError)
async def connection_unavailable(request, error):
    return JSONResponse(status_code=503, content={
        'detail': 'Supabase no está disponible. Solo se pueden consultar carritos guardados y encolar su cierre.'
    })

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas de API v1
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", tags=["Health"])
def health_check():
    supabase_status = "unknown"
    try:
        supabase = get_supabase_client()
        supabase.table("productos").select("id").limit(1).execute()
        supabase_status = "connected"
    except Exception as e:
        supabase_status = f"error: {str(e)}"

    return {
        "status": "healthy" if supabase_status == "connected" else "degraded",
        "supabase": supabase_status,
        "database": "PostgreSQL (Supabase)",
        "realtime": "Enabled"
    }


@app.get('/api/v1/resiliencia', tags=['Operaciones Dev E'])
def resilience_status():
    return get_checkout_queue().status()


@app.get('/live', tags=['Health'])
def liveness():
    return {'status': 'alive'}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
