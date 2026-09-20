"""Incident tracking endpoints.

POST /incidents               - report an incident for a robot (operator/admin).
GET  /incidents                - list incidents, optionally filtered (any role).
GET  /incidents/{incident_id}  - get one incident (any role).
POST /incidents/{incident_id}/resolve - mark an incident resolved (operator/admin).

Incident creation is a normal authenticated REST write, not routed through
the agent's confirmation flow (backend/app/agent/confirmations.py) — that
flow exists because sending a robot command changes real-world robot
behavior and is hard to undo. An incident row is an internal, fully
reversible record, so it's the same risk class as any other write in this
app. Only a read tool (get_recent_incidents in backend/app/agent/tools.py)
is exposed to the LLM; there is no agent-facing write tool for incidents.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.auth import ROLE_ADMIN, ROLE_OPERATOR, get_current_user, require_role
from backend.app.database import get_db
from backend.app.models.incident import Incident
from backend.app.models.robot import Robot
from backend.app.models.user import User
from backend.app.schemas.incident import IncidentCreateRequest, IncidentResolveRequest, IncidentResponse

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = logging.getLogger("backend.app.incidents")


def create_incident(
    db: Session, *, robot_id: str, title: str, description: str, severity: str, created_by: int
) -> Incident:
    """The single implementation of "how an incident gets created" — used by
    the route below and, in principle, reusable elsewhere without a second
    copy of this logic.
    """
    incident = Incident(
        robot_id=robot_id,
        title=title,
        description=description,
        severity=severity,
        status="open",
        created_by=created_by,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def resolve_incident(db: Session, *, incident_id: int, resolution_notes: str | None) -> Incident:
    incident = db.get(Incident, incident_id)

    if incident is None:
        raise ValueError("not_found")

    if incident.status == "resolved":
        raise ValueError("already_resolved")

    incident.status = "resolved"
    incident.resolved_at = datetime.now(timezone.utc)
    incident.resolution_notes = resolution_notes
    db.commit()
    db.refresh(incident)
    return incident


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def report_incident(
    request: IncidentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
):
    if db.get(Robot, request.robot_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot not found")

    incident = create_incident(
        db,
        robot_id=request.robot_id,
        title=request.title,
        description=request.description,
        severity=request.severity,
        created_by=current_user.id,
    )

    logger.info(
        "incidents.created",
        extra={"user_id": current_user.id, "robot_id": request.robot_id, "incident_id": incident.id},
    )

    return incident


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    robot_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Incident)

    if robot_id is not None:
        query = query.filter(Incident.robot_id == robot_id)

    if status_filter is not None:
        query = query.filter(Incident.status == status_filter)

    return query.order_by(desc(Incident.created_at), desc(Incident.id)).limit(limit).all()


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    incident = db.get(Incident, incident_id)

    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    return incident


@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
def resolve_incident_route(
    incident_id: int,
    request: IncidentResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
):
    try:
        incident = resolve_incident(db, incident_id=incident_id, resolution_notes=request.resolution_notes)
    except ValueError as exc:
        if str(exc) == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Incident is already resolved")

    logger.info(
        "incidents.resolved",
        extra={"user_id": current_user.id, "incident_id": incident.id},
    )

    return incident
