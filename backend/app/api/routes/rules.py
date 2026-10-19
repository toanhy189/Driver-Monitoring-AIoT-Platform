from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.deps import require_admin
from app.core.config import settings
from app.core.db import get_session
from app.models.ai_event import RuleBinding
from app.models.user import User
from app.schemas.rules import RuleBindingRequest, RulePolicy
from app.services.access import assigned_device


router = APIRouter(tags=["rules"])


@router.get("/devices/{device_id}/rule")
def get_rule(device_id: int, current_user: User = Depends(require_admin), session: Session = Depends(get_session)):
    assigned_device(session, current_user.id, device_id)
    binding = session.get(RuleBinding, device_id)
    return {"source_device_id": device_id, "target_device_id": binding.target_device_id if binding else None,
            "enabled": binding.enabled if binding else False,
            "effective_enabled": bool(settings.RULE_ENGINE_ENABLED and binding and binding.enabled),
            "policy": binding.policy if binding else RulePolicy().model_dump(),
            "policy_note": "Sample defaults require agreement with TV1/TV3 before enabling"}


@router.put("/devices/{device_id}/rule")
def put_rule(device_id: int, data: RuleBindingRequest, current_user: User = Depends(require_admin),
             session: Session = Depends(get_session)):
    source = assigned_device(session, current_user.id, device_id)
    target = assigned_device(session, current_user.id, data.target_device_id)
    if source.device_type != "VISION_NODE" or target.device_type != "ALERT_NODE":
        raise HTTPException(status_code=409, detail="Rule must connect a Vision Node to an Alert Node")
    if source.lifecycle_state == "DECOMMISSIONED" or target.lifecycle_state == "DECOMMISSIONED":
        raise HTTPException(status_code=409, detail="Device decommissioned")
    binding = session.get(RuleBinding, device_id) or RuleBinding(source_device_id=device_id,
                target_device_id=target.id, policy=data.policy.model_dump())
    binding.target_device_id = target.id
    binding.enabled = data.enabled
    binding.policy = data.policy.model_dump()
    binding.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(binding)
    session.commit()
    return get_rule(device_id, current_user, session)
