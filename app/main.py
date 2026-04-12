from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.router import router as agent_router
from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.department.router import router as department_router
from app.knowledge.chunk_router import router as chunk_router
from app.knowledge.document_router import router as document_router
from app.knowledge.export_router import router as export_router
from app.knowledge.folder_router import router as folder_router
from app.knowledge.retrieval_router import router as retrieval_router
from app.knowledge.router import router as kb_router
from app.model.router import router as model_router
from app.system.init_router import router as init_router
from app.system.notification_router import router as notification_router
from app.system.router import router as system_router

setup_logging()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(department_router, prefix=settings.API_V1_PREFIX)
app.include_router(model_router, prefix=settings.API_V1_PREFIX)
app.include_router(system_router, prefix=settings.API_V1_PREFIX)
app.include_router(init_router, prefix=settings.API_V1_PREFIX)
app.include_router(notification_router, prefix=settings.API_V1_PREFIX)
app.include_router(kb_router, prefix=settings.API_V1_PREFIX)
app.include_router(folder_router, prefix=settings.API_V1_PREFIX)
app.include_router(document_router, prefix=settings.API_V1_PREFIX)
app.include_router(chunk_router, prefix=settings.API_V1_PREFIX)
app.include_router(export_router, prefix=settings.API_V1_PREFIX)
app.include_router(retrieval_router, prefix=settings.API_V1_PREFIX)
app.include_router(agent_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)
