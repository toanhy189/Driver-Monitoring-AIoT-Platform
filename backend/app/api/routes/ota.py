import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import require_admin
from app.core.config import settings
from app.core.db import get_session
from app.models.device import Device
from app.models.user import User
from app.models.ai_event import RuleBinding
from app.models.ota import FirmwareArtifact, OtaDeployment, OtaJob, utcnow
from app.schemas.ota import FirmwareManifest, DeploymentRequest
from app.services.audit_service import log_action
from app.services import ota_service as service

router = APIRouter(prefix="/ota",tags=["firmware-ota"])

@router.get("/firmware")
def firmware_list(user: User=Depends(require_admin),session: Session=Depends(get_session)):
    return {"configuration":service.configuration(),"items":[service.artifact_public(item) for item in
        session.exec(select(FirmwareArtifact).order_by(FirmwareArtifact.id.desc()).limit(200)).all()]}

@router.post("/firmware",status_code=201)
def upload_firmware(file: UploadFile=File(),manifest: str=Form(),notes: str=Form(default="",max_length=2000),
                    user: User=Depends(require_admin),session: Session=Depends(get_session)):
    try:
        signed = FirmwareManifest.model_validate_json(manifest)
        data = file.file.read(2097153)
        if len(data)>2097152: raise HTTPException(413,"Firmware tối đa 2 MiB.")
        if len(data)!=signed.size_bytes or hashlib.sha256(data).hexdigest()!=signed.sha256:
            raise ValueError("File không khớp kích thước/hash trong manifest.")
        app_digest = service.image_digest(data)
    except ValueError as error:
        raise HTTPException(422,str(error)) from None
    settings.OTA_STORAGE_DIR.mkdir(parents=True,exist_ok=True)
    key = uuid4().hex+".bin"
    path = settings.OTA_STORAGE_DIR/key
    with path.open("xb") as output: output.write(data)
    artifact = FirmwareArtifact(version=signed.version,hardware_version=signed.hardware_version,
        sha256=signed.sha256,app_sha256=app_digest,size_bytes=len(data),storage_key=key,
        manifest=signed.model_dump(),notes=notes,created_by=user.id)
    session.add(artifact)
    try:
        session.flush()
        log_action(session,user.id,"UPLOAD_FIRMWARE","FirmwareArtifact",str(artifact.id),
            {"version":artifact.version,"sha256":artifact.sha256})
        session.commit()
    except Exception as error:
        session.rollback();path.unlink(missing_ok=True)
        if isinstance(error,IntegrityError): raise HTTPException(409,"Phiên bản cho phần cứng này đã tồn tại.") from None
        raise
    session.refresh(artifact)
    return service.artifact_public(artifact)

def find_artifact(session,identifier,lock=False):
    query = select(FirmwareArtifact).where(FirmwareArtifact.id==identifier)
    item = session.exec(query.with_for_update() if lock else query).first()
    if item is None: raise HTTPException(404,"Firmware not found")
    return item

@router.post("/firmware/{artifact_id}/verify")
def verify_firmware(artifact_id: int,user: User=Depends(require_admin),session: Session=Depends(get_session)):
    artifact = find_artifact(session,artifact_id,True)
    if artifact.state not in {"DRAFT","VERIFIED"}: raise HTTPException(409,"Chỉ xác minh bản nháp/chưa phát hành.")
    try: service.verify_artifact(artifact)
    except Exception:
        artifact.verification_error="Chữ ký, hash hoặc khóa xác minh không hợp lệ."
        session.add(artifact);session.commit()
        raise HTTPException(422,artifact.verification_error) from None
    artifact.state="VERIFIED";artifact.verification_error=None;session.add(artifact)
    log_action(session,user.id,"VERIFY_FIRMWARE","FirmwareArtifact",str(artifact.id));session.commit()
    return service.artifact_public(artifact)

@router.post("/firmware/{artifact_id}/release")
def release_firmware(artifact_id: int,user: User=Depends(require_admin),session: Session=Depends(get_session)):
    artifact = find_artifact(session,artifact_id,True)
    if artifact.state != "VERIFIED": raise HTTPException(409,"Cần xác minh firmware trước khi phát hành.")
    try: service.verify_artifact(artifact)
    except Exception: raise HTTPException(422,"Firmware không còn khớp chữ ký.") from None
    artifact.state="RELEASED";session.add(artifact)
    log_action(session,user.id,"RELEASE_FIRMWARE","FirmwareArtifact",str(artifact.id));session.commit()
    return service.artifact_public(artifact)

@router.post("/firmware/{artifact_id}/withdraw")
def withdraw_firmware(artifact_id: int,user: User=Depends(require_admin),session: Session=Depends(get_session)):
    artifact = find_artifact(session,artifact_id,True)
    artifact.state="WITHDRAWN";session.add(artifact)
    log_action(session,user.id,"WITHDRAW_FIRMWARE","FirmwareArtifact",str(artifact.id));session.commit()
    return service.artifact_public(artifact)

def selected_devices(session,data,lock=False):
    identifiers=sorted(set(data.device_ids))
    if any(item<=0 for item in identifiers) or len(identifiers)!=len(data.device_ids):
        raise HTTPException(422,"Danh sách thiết bị không hợp lệ hoặc bị trùng.")
    query=select(Device).where(Device.id.in_(identifiers)).order_by(Device.id)
    devices=session.exec(query.with_for_update().execution_options(populate_existing=True) if lock else query).all()
    if len(devices)!=len(identifiers): raise HTTPException(404,"Device not found")
    return devices

@router.get("/devices")
def candidate_devices(user: User=Depends(require_admin),session: Session=Depends(get_session)):
    return [{"id":d.id,"device_code":d.device_code,"name":d.name,"firmware_version":d.firmware_version,
        "hardware_version":d.hardware_version,"status":d.status,"lifecycle_state":d.lifecycle_state,
        "ota_capabilities":d.ota_capabilities} for d in session.exec(select(Device).where(
            Device.device_type=="ALERT_NODE",Device.lifecycle_state!="DECOMMISSIONED").order_by(Device.id)).all()]

@router.post("/deployments/preview")
def preview_deployment(data: DeploymentRequest,user: User=Depends(require_admin),session: Session=Depends(get_session)):
    artifact=find_artifact(session,data.artifact_id)
    rows=[{"id":d.id,"device_code":d.device_code,"current_version":d.firmware_version,
        "target_version":artifact.version,"reason":service.eligibility(session,d,artifact)} for d in selected_devices(session,data)]
    return {"ready":all(row["reason"] is None for row in rows),"devices":rows,
        "notice":"Thiết bị sẽ vào bảo trì và tắt liên kết cảnh báo tự động. Hoàn tất cần kích hoạt lại riêng."}

@router.post("/deployments",status_code=201)
def create_deployment(data: DeploymentRequest,user: User=Depends(require_admin),session: Session=Depends(get_session)):
    if not data.confirmed: raise HTTPException(422,"Cần xác nhận cập nhật firmware.")
    artifact=find_artifact(session,data.artifact_id)
    devices=selected_devices(session,data,True)
    for device in devices:
        reason=service.eligibility(session,device,artifact)
        if reason: raise HTTPException(409,device.device_code+": "+reason)
    try: service.verify_artifact(artifact)
    except Exception: raise HTTPException(422,"Firmware hoặc chữ ký không hợp lệ.") from None
    deployment=OtaDeployment(artifact_id=artifact.id,created_by=user.id)
    session.add(deployment);session.flush()
    for device in devices:
        device.lifecycle_state="MAINTENANCE";session.add(device)
        for binding in session.exec(select(RuleBinding).where(RuleBinding.target_device_id==device.id)).all():
            binding.enabled=False;binding.updated_at=utcnow();session.add(binding)
        job=OtaJob(deployment_id=deployment.id,device_id=device.id,request_id="ota-"+uuid4().hex,
            previous_version=device.firmware_version,previous_sha256=device.ota_capabilities["image_sha256"],
            expires_at=utcnow()+timedelta(minutes=10))
        session.add(job);session.flush();service.add_event(session,job,"QUEUED","Đã tạo; thiết bị vào bảo trì.")
    log_action(session,user.id,"CREATE_OTA_DEPLOYMENT","OtaDeployment",str(deployment.id),
        {"artifact_id":artifact.id,"device_ids":data.device_ids});session.commit()
    return {"id":deployment.id,"message":"Đã tạo đợt cập nhật"}

@router.get("/deployments")
def list_deployments(user: User=Depends(require_admin),session: Session=Depends(get_session)):
    deployments=session.exec(select(OtaDeployment).order_by(OtaDeployment.id.desc()).limit(50)).all()
    return [{**service.public_fields(deployment),"jobs":[service.job_public(session,job) for job in session.exec(
        select(OtaJob).where(OtaJob.deployment_id==deployment.id).order_by(OtaJob.id)).all()]} for deployment in deployments]

@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int,user: User=Depends(require_admin),session: Session=Depends(get_session)):
    job=session.get(OtaJob,job_id)
    if job is None: raise HTTPException(404,"OTA job not found")
    session.exec(select(Device).where(Device.id==job.device_id).with_for_update()).one()
    job=session.exec(select(OtaJob).where(OtaJob.id==job_id).with_for_update()
        .execution_options(populate_existing=True)).one()
    if job.state!="QUEUED": raise HTTPException(409,"Chỉ hủy phần chưa gửi; không thể thu hồi firmware đã gửi.")
    job.state="CANCELLED";job.updated_at=utcnow();session.add(job);service.add_event(session,job,job.state)
    log_action(session,user.id,"CANCEL_OTA_JOB","OtaJob",str(job.id));session.commit()
    return {"id":job.id,"state":job.state}

@router.get("/device/jobs/{job_id}/image")
def device_image(job_id: int,authorization: str=Header(default=""),session: Session=Depends(get_session)):
    try:
        claims=jwt.decode(authorization.removeprefix("Bearer "),settings.SECRET_KEY,algorithms=["HS256"],audience="ota-download")
    except jwt.PyJWTError: raise HTTPException(401,"Invalid OTA download credential") from None
    job=session.get(OtaJob,job_id)
    if not job or claims.get("job")!=job_id or claims.get("sub")!=str(job.device_id) or claims.get("req")!=job.request_id:
        raise HTTPException(403,"OTA credential scope mismatch")
    device=session.get(Device,job.device_id)
    if device.lifecycle_state!="MAINTENANCE" or job.expires_at<=utcnow() or job.state not in {"PUBLISHING","SENT","ACCEPTED","DOWNLOADING","VERIFYING"}:
        raise HTTPException(409,"OTA download is no longer available")
    artifact=find_artifact(session,session.get(OtaDeployment,job.deployment_id).artifact_id)
    if artifact.state!="RELEASED": raise HTTPException(409,"Firmware was withdrawn")
    return FileResponse(service.artifact_path(artifact),media_type="application/octet-stream",
        headers={"Cache-Control":"no-store","X-Firmware-SHA256":artifact.sha256})
