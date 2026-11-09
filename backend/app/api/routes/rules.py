from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api.deps import require_admin
from app.core.config import settings
from app.core.db import get_session
from app.models.ai_event import RuleBinding
from app.models.device import Device
from app.models.user import User
from app.schemas.rules import RuleBindingRequest, RulePolicy
from app.services.access import assigned_device
from app.services.audit_service import log_action
from app.services.rule_binding import (active_source_for_target, binding_status,
    cancel_binding_commands, device_summary, has_inflight_commands, revision)


router = APIRouter(tags=["rules"])


@router.get("/devices/{device_id}/rule")
def get_rule(device_id: int, current_user: User = Depends(require_admin), session: Session = Depends(get_session)):
    source = assigned_device(session, current_user, device_id)
    binding = session.get(RuleBinding, device_id)
    occupied = dict(session.exec(select(RuleBinding.target_device_id, RuleBinding.source_device_id)
        .join(Device, Device.id == RuleBinding.source_device_id).where(
            RuleBinding.enabled.is_(True), RuleBinding.source_device_id != device_id,
            Device.lifecycle_state != "DECOMMISSIONED")).all())
    targets = []
    for target in session.exec(select(Device).where(Device.device_type == "ALERT_NODE",
            Device.lifecycle_state != "DECOMMISSIONED").order_by(Device.device_code)).all():
        targets.append({**device_summary(target), "active_source_id": occupied.get(target.id)})
    return {"source_device_id": device_id, "target_device_id": binding.target_device_id if binding else None,
            "enabled": binding.enabled if binding else False,
            "effective_enabled": bool(settings.RULE_ENGINE_ENABLED and binding and binding.enabled),
            "policy": binding.policy if binding else RulePolicy().model_dump(),
            "policy_note": "driver-bench-20261107-v1 uses the agreed bench preset; legacy defaults remain separate",
            "updated_at": revision(binding), "engine_enabled": settings.RULE_ENGINE_ENABLED,
            "readiness": binding_status(session, source, binding), "targets": targets}


@router.put("/devices/{device_id}/rule")
def put_rule(device_id: int, data: RuleBindingRequest, current_user: User = Depends(require_admin),
             session: Session = Depends(get_session)):
    source = assigned_device(session, current_user, device_id)
    # Same source lock as event ingestion and dispatch. Serialize edits before
    # marking a command PUBLISHING; already published work cannot be recalled.
    source = session.exec(select(Device).where(Device.id == source.id).with_for_update()
                          .execution_options(populate_existing=True)).one()
    binding = session.exec(select(RuleBinding).where(RuleBinding.source_device_id == device_id)
                           .execution_options(populate_existing=True)).first()
    if "expected_updated_at" in data.model_fields_set and data.expected_updated_at != revision(binding):
        raise HTTPException(status_code=409, detail="Liên kết đã được người khác thay đổi. Hãy tải lại trước khi lưu.")
    assigned_device(session, current_user, data.target_device_id)
    target_ids = sorted({data.target_device_id} | ({binding.target_device_id} if binding else set()))
    targets = session.exec(select(Device).where(Device.id.in_(target_ids)).order_by(Device.id)
                           .with_for_update().execution_options(populate_existing=True)).all()
    target = next(item for item in targets if item.id == data.target_device_id)
    if source.device_type != "VISION_NODE" or target.device_type != "ALERT_NODE":
        raise HTTPException(status_code=409, detail="Rule must connect a Vision Node to an Alert Node")
    disabling_existing = binding is not None and binding.target_device_id == target.id and not data.enabled
    if (source.lifecycle_state == "DECOMMISSIONED" or target.lifecycle_state == "DECOMMISSIONED") and not disabling_existing:
        raise HTTPException(status_code=409, detail="Device decommissioned")
    target_changed = binding is not None and binding.target_device_id != target.id
    enabled = data.enabled and not target_changed and (binding is not None or "expected_updated_at" not in data.model_fields_set)
    if enabled and (source.lifecycle_state != "ACTIVE" or target.lifecycle_state != "ACTIVE"):
        raise HTTPException(status_code=409, detail="Camera và thiết bị nhận phải được kích hoạt trước khi bật tự động.")
    if enabled and active_source_for_target(session, target.id, device_id):
        raise HTTPException(status_code=409, detail="ESP32 này đang nhận cảnh báo tự động từ camera khác.")
    if enabled and (not binding or not binding.enabled) and has_inflight_commands(session, device_id):
        raise HTTPException(status_code=409, detail="Lệnh trước còn đang gửi hoặc chờ phản hồi. Kiểm tra lịch sử trước khi bật lại.")
    policy = data.policy.model_dump()
    changed = binding is None or target_changed or binding.enabled != enabled or binding.policy != policy
    if binding and changed:
        cancel_binding_commands(session, device_id)
    previous_revision = binding.updated_at if binding else None
    binding = binding or RuleBinding(source_device_id=device_id, target_device_id=target.id, policy=policy)
    binding.target_device_id = target.id
    binding.enabled = enabled
    binding.policy = policy
    if changed:
        stamp = datetime.now(timezone.utc).replace(tzinfo=None)
        binding.updated_at = max(stamp, previous_revision + timedelta(microseconds=1)) if previous_revision else stamp
    session.add(binding)
    # Rule change truoc day khong co audit; ghi target/enabled, khong luu payload tuy y.
    log_action(
        session, current_user.id, "UPDATE_RULE_BINDING", "RuleBinding", str(device_id),
        {"target_device_id": target.id, "enabled": binding.enabled},
    )
    session.commit()
    return get_rule(device_id, current_user, session)
