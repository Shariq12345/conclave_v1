from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from conclave.server.registry import ServiceRegistry
from conclave.server.authz import require_permission

router = APIRouter(prefix="/trainings", tags=["Trainings"])


class TrainingCreate(BaseModel):
    name: str
    participating_clients: List[str]
    assigned_policy: str
    dataset_name: str
    description: str = ""
    priority: str = "Medium"


@router.post("/create")
def create_session(data: TrainingCreate, current_user=Depends(require_permission("manage_training"))):
    service = ServiceRegistry().training_service
    session = service.create_session(
        name=data.name,
        client_names=data.participating_clients,
        policy_name=data.assigned_policy,
        dataset_name=data.dataset_name,
        description=data.description,
        priority=data.priority,
    )
    return session.to_dict()


@router.get("/list")
def list_sessions(current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().training_service
    sessions = service.list_sessions()
    return [s.to_dict() for s in sessions]


@router.get("/show/{name}")
def show_session(name: str, current_user=Depends(require_permission("view_audit"))):
    service = ServiceRegistry().training_service
    session = service.get_session(name)
    return session.to_dict()


@router.post("/start/{name}")
def start_session(name: str, current_user=Depends(require_permission("manage_training"))):
    service = ServiceRegistry().training_service
    session, validation_result = service.start_session(name)
    return {
        "session": session.to_dict(),
        "validation_result": validation_result.to_dict(),
    }


@router.post("/stop/{name}")
def stop_session(name: str, current_user=Depends(require_permission("manage_training"))):
    service = ServiceRegistry().training_service
    session = service.stop_session(name)
    return session.to_dict()


@router.delete("/remove/{name}")
def remove_session(name: str, current_user=Depends(require_permission("manage_training"))):
    service = ServiceRegistry().training_service
    success = service.remove_session(name)
    return {"success": success}

