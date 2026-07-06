from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# ── Load environment variables from .env file ────────────────────────────────
import os

def load_dotenv(dotenv_path=".env"):
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    # Set value if not already set in OS environment
                    os.environ.setdefault(key, val)

load_dotenv()

def patch_uvicorn_transport():
    try:
        from uvicorn.protocols.http.h11_impl import RequestResponseCycle as H11Cycle
        original_h11_init = H11Cycle.__init__
        def patched_h11_init(self, scope, conn, transport, *args, **kwargs):
            scope["transport"] = transport
            original_h11_init(self, scope, conn, transport, *args, **kwargs)
        H11Cycle.__init__ = patched_h11_init
    except Exception:
        pass

    try:
        from uvicorn.protocols.http.httptools_impl import RequestResponseCycle as HttpToolsCycle
        original_httptools_init = HttpToolsCycle.__init__
        def patched_httptools_init(self, scope, conn, transport, *args, **kwargs):
            scope["transport"] = transport
            original_httptools_init(self, scope, conn, transport, *args, **kwargs)
        HttpToolsCycle.__init__ = patched_httptools_init
    except Exception:
        pass

patch_uvicorn_transport()

from conclave.server.services import (
    DuplicateClientError, ClientNotFoundError,
    DuplicatePolicyError, PolicyNotFoundError,
    DuplicateConsentError, ConsentNotFoundError,
    DuplicateTrainingError, TrainingNotFoundError,
    TrainingValidationError, AuditNotFoundError,
    DuplicateOrganizationError, OrganizationNotFoundError,
    DuplicateUserError, UserNotFoundError,
    InvalidCredentialsError, InactiveUserError, AuthenticationError,
    JoinRequestNotFoundError, JoinRequestAlreadyExistsError,
    NodeNotFoundError
)

app = FastAPI(title="Conclave Governance Server", version="0.1.0")

# 1. Custom Exception Handlers to return clear HTTP details
@app.exception_handler(ClientNotFoundError)
@app.exception_handler(PolicyNotFoundError)
@app.exception_handler(ConsentNotFoundError)
@app.exception_handler(TrainingNotFoundError)
@app.exception_handler(AuditNotFoundError)
@app.exception_handler(OrganizationNotFoundError)
@app.exception_handler(UserNotFoundError)
@app.exception_handler(NodeNotFoundError)
def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(DuplicateClientError)
@app.exception_handler(DuplicatePolicyError)
@app.exception_handler(DuplicateConsentError)
@app.exception_handler(DuplicateTrainingError)
@app.exception_handler(DuplicateOrganizationError)
@app.exception_handler(DuplicateUserError)
@app.exception_handler(ValueError)
def bad_request_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

@app.exception_handler(InvalidCredentialsError)
@app.exception_handler(InactiveUserError)
@app.exception_handler(AuthenticationError)
def auth_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=401, content={"detail": str(exc)})

@app.exception_handler(JoinRequestNotFoundError)
def join_not_found_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(JoinRequestAlreadyExistsError)
def join_conflict_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.exception_handler(TrainingValidationError)
def training_validation_handler(request: Request, exc: TrainingValidationError):
    content = {"detail": str(exc)}
    if exc.validation_result:
        content["validation_result"] = exc.validation_result.to_dict()
    return JSONResponse(status_code=400, content=content)

# 2. Register REST API Routers
from conclave.server.api.client import router as client_router
from conclave.server.api.policy import router as policy_router
from conclave.server.api.consent import router as consent_router
from conclave.server.api.training import router as training_router
from conclave.server.api.audit import router as audit_router
from conclave.server.api.organization import router as organization_router
from conclave.server.api.user import router as user_router
from conclave.server.api.auth import router as auth_router
from conclave.server.api.onboarding import router as onboarding_router
from conclave.server.api.node import router as node_router
from conclave.server.api.monitor import router as monitor_router
from conclave.server.api.notification import router as notification_router
from conclave.server.api.report import router as report_router

app.include_router(onboarding_router)  # Public first — no auth required
app.include_router(auth_router)
app.include_router(client_router)
app.include_router(policy_router)
app.include_router(consent_router)
app.include_router(training_router)
app.include_router(audit_router)
app.include_router(organization_router)
app.include_router(user_router)
app.include_router(node_router)
app.include_router(monitor_router)
app.include_router(notification_router)
app.include_router(report_router)


# ── WebSocket Alert Stream Gateway ──────────────────────────────────────────
from fastapi import WebSocket, WebSocketDisconnect
from conclave.server.notifications import ws_manager

@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Maintain active connection and ignore any incoming client frames
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# 3. Server Startup script helper
def start():
    import uvicorn
    import os
    host = os.getenv("CONCLAVE_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("CONCLAVE_SERVER_PORT", "8000"))
    uvicorn.run("conclave.server.main:app", host=host, port=port, reload=True)
