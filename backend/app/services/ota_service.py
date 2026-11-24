"""Signed OTA artifacts, device guards, persisted dispatch and reported outcomes."""
import base64
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import jwt
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException
from sqlmodel import Session, select

from app.core.config import settings
from app.models.device import Device
from app.models.command import Command
from app.models.ai_event import RuleBinding
from app.models.ota import FirmwareArtifact, OtaDeployment, OtaJob, OtaJobEvent, utcnow
from app.schemas.ota import FirmwareManifest, OtaCapabilities, OtaStatus, signing_bytes

logger = logging.getLogger(__name__)
FINAL = {"CONFIRMED","REJECTED","FAILED","CANCELLED","ROLLED_BACK"}
RANK = {"QUEUED":0,"PUBLISHING":0,"SENT":0,"ACCEPTED":1,"DOWNLOADING":2,"VERIFYING":3,"REBOOTING":4}
BUILD_MARKER=b"driver-ota-capable-v1;bootloader-rollback;RSA2048-SHA256"

def trusted_key():
    key = serialization.load_pem_public_key(settings.OTA_PUBLIC_KEY_FILE.read_bytes())
    if not isinstance(key,rsa.RSAPublicKey) or key.key_size != 2048:
        raise ValueError("OTA requires an RSA-2048 public key")
    return key

def key_fingerprint():
    return hashlib.sha256(trusted_key().public_bytes(
        serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()

def configuration():
    try:
        fingerprint = key_fingerprint()
    except (OSError,ValueError):
        fingerprint = None
    origin = urlsplit(settings.OTA_PUBLIC_BASE_URL)
    valid_url = bool(origin.hostname and not origin.username and not origin.password and not origin.query
        and not origin.fragment and origin.path in ("", "/") and (origin.scheme == "https" or
        (settings.OTA_ALLOW_HTTP_FOR_LAN and origin.scheme == "http")))
    return {"enabled":settings.OTA_ENABLED,"public_key_ready":bool(fingerprint),
        "key_sha256":fingerprint,"download_origin_ready":valid_url,
        "transport":"HTTPS" if origin.scheme == "https" else "HTTP_LAN" if valid_url else "UNCONFIGURED",
        "note":"Thiết bị cần firmware OTA nền, đúng khóa ký và địa chỉ máy chủ. Cập nhật xong vẫn ở chế độ bảo trì."}

def artifact_path(artifact):
    path = settings.OTA_STORAGE_DIR / artifact.storage_key
    if path.parent.resolve() != settings.OTA_STORAGE_DIR.resolve() or not path.is_file():
        raise HTTPException(404,"Firmware file not found")
    return path

def image_digest(data):
    # ESP32 application image with appended digest, not a merged whole-flash image.
    if len(data) < 256 or data[0] != 0xe9 or int.from_bytes(data[12:14],"little") != 0 or data[23] != 1:
        raise ValueError("Cần application firmware.bin ESP32 có SHA-256, không dùng merged/bootloader image.")
    if BUILD_MARKER not in data: raise ValueError("Firmware thiếu giao thức OTA/rollback tương thích; không dùng bản legacy.")
    digest = hashlib.sha256(data[:-32]).digest()
    if data[-32:] != digest:
        raise ValueError("ESP32 application image checksum is invalid")
    offset=24; checksum=0xef
    if not 1<=data[1]<=16: raise ValueError("Invalid ESP32 segment count")
    for _ in range(data[1]):
        if offset+8>len(data)-32: raise ValueError("Truncated ESP32 segment header")
        size=int.from_bytes(data[offset+4:offset+8],"little");offset+=8
        if offset+size>len(data)-32: raise ValueError("Truncated ESP32 segment data")
        for value in data[offset:offset+size]: checksum^=value
        offset+=size
    checksum_offset=offset | 15
    if checksum_offset+33!=len(data) or data[checksum_offset]!=checksum:
        raise ValueError("Invalid ESP32 segment checksum")
    return digest.hex()

def verify_artifact(artifact):
    manifest = FirmwareManifest.model_validate(artifact.manifest)
    data = artifact_path(artifact).read_bytes()
    if len(data) != manifest.size_bytes or hashlib.sha256(data).hexdigest() != manifest.sha256:
        raise ValueError("Firmware size/hash mismatch")
    if image_digest(data) != artifact.app_sha256:
        raise ValueError("Application digest mismatch")
    trusted_key().verify(base64.b64decode(manifest.signature,validate=True),signing_bytes(manifest),
        padding.PKCS1v15(),hashes.SHA256())
    pem=trusted_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).strip()
    if pem not in data: raise ValueError("Firmware không chứa đúng khóa xác minh OTA.")

def public_fields(item):
    values={name:getattr(item,name) for name in type(item).model_fields}
    return {key:value.isoformat()+"Z" if isinstance(value,datetime) and value.tzinfo is None else value
        for key,value in values.items()}

def artifact_public(artifact):
    fields=public_fields(artifact)
    return {key:fields[key] for key in ("id","version","hardware_version","sha256","app_sha256",
        "size_bytes","state","notes","verification_error","created_by","created_at")}

def recent(device):
    return bool(device.last_seen and -5 <= (utcnow()-device.last_seen).total_seconds() <= 30)

def hardware_reason(device,artifact,expected_state="ACTIVE"):
    config = configuration()
    if not config["enabled"]: return "OTA toàn hệ thống chưa được bật."
    if not config["public_key_ready"] or not config["download_origin_ready"]: return "Chưa cấu hình khóa ký hoặc địa chỉ tải firmware."
    if device.device_type != "ALERT_NODE": return "OTA chỉ áp dụng cho bộ cảnh báo ESP32."
    if device.lifecycle_state != expected_state: return "Thiết bị chưa ở trạng thái phù hợp: " + expected_state
    if device.status != "ONLINE" or not recent(device): return "Thiết bị offline hoặc heartbeat đã cũ."
    if device.hardware_version != artifact.hardware_version: return "Firmware không tương thích phiên bản phần cứng."
    try: caps = OtaCapabilities.model_validate(device.ota_capabilities)
    except ValueError: return "Thiết bị chưa báo hỗ trợ OTA; cần nạp firmware nền qua USB."
    if not caps.supported or not caps.rollback_supported: return "Thiết bị chưa hỗ trợ OTA/rollback đầy đủ."
    if caps.key_sha256 != config["key_sha256"]: return "Khóa xác minh trên thiết bị không khớp khóa Backend."
    if artifact.size_bytes > caps.max_image_bytes: return "Firmware lớn hơn phân vùng cập nhật."
    if caps.outputs_busy: return "LED/còi/motor đang chạy."
    if device.firmware_version == artifact.version: return "Thiết bị đã chạy phiên bản này."
    return None

def eligibility(session,device,artifact):
    reason = hardware_reason(device,artifact,"MAINTENANCE" if device.lifecycle_state=="MAINTENANCE" else "ACTIVE")
    if reason: return reason
    if artifact.state != "RELEASED": return "Firmware chưa được phát hành hoặc đã thu hồi."
    if session.exec(select(OtaJob.id).where(OtaJob.device_id==device.id,~OtaJob.state.in_(FINAL))).first():
        return "Thiết bị còn đợt OTA chưa có kết quả chắc chắn."
    commands = session.exec(select(Command).where(Command.device_id==device.id,
        Command.created_at >= utcnow()-timedelta(seconds=settings.COMMAND_TIMEOUT_SECONDS+10))).all()
    for command in commands:
        if command.status in {"PENDING","SENT","ACKNOWLEDGED"} and command.ack_status != "COMPLETED":
            return "Thiết bị còn lệnh đang gửi hoặc chờ ACK."
        if any(child.get("dispatch_state") in {"QUEUED","PUBLISHING","PUBLISHED"} and
            child.get("status") not in {"COMPLETED","FAILED"} for child in (command.dispatches or {}).values()):
            return "Thiết bị còn tải chưa xác nhận kết thúc."
    return None

def add_event(session,job,state,detail=None,event_id=None,received=0):
    session.add(OtaJobEvent(job_id=job.id,event_id=event_id or "server-"+uuid4().hex,
        state=state,detail=detail,bytes_received=received))

def job_public(session,job):
    deployment = session.get(OtaDeployment,job.deployment_id)
    artifact = session.get(FirmwareArtifact,deployment.artifact_id)
    device = session.get(Device,job.device_id)
    previous = session.exec(select(FirmwareArtifact).where(FirmwareArtifact.app_sha256==job.previous_sha256,
        FirmwareArtifact.version==job.previous_version,FirmwareArtifact.hardware_version==artifact.hardware_version,
        FirmwareArtifact.state=="RELEASED")).first()
    return {**public_fields(job),"device_code":device.device_code,"target_version":artifact.version,
        "size_bytes":artifact.size_bytes,"progress_percent":round(100*job.bytes_received/artifact.size_bytes),
        "previous_artifact_id":previous.id if previous else None,
        "events":[public_fields(item) for item in session.exec(select(OtaJobEvent).where(
            OtaJobEvent.job_id==job.id).order_by(OtaJobEvent.id)).all()]}

def accept_status(session,code,payload):
    status = OtaStatus.model_validate(payload)
    device = session.exec(select(Device).where(Device.device_code==code).with_for_update()).first()
    if not device or device.device_type != "ALERT_NODE" or device.lifecycle_state == "DECOMMISSIONED" or status.device_code != code:
        return []
    job = session.exec(select(OtaJob).where(OtaJob.id==status.job_id).with_for_update()).first()
    if not job or job.device_id != device.id or job.request_id != status.request_id or job.state in FINAL or status.sequence <= job.last_sequence:
        return []
    if job.state == "QUEUED": return []
    if status.state in RANK and (job.state == "RESULT_UNKNOWN" or RANK[status.state] < RANK.get(job.state,0)):
        return []
    artifact = session.get(FirmwareArtifact,session.get(OtaDeployment,job.deployment_id).artifact_id)
    if status.bytes_received > artifact.size_bytes: return []
    if status.state == "CONFIRMED" and not (status.firmware_version==artifact.version and
            status.image_sha256==artifact.app_sha256 and status.download_sha256==artifact.sha256):
        return []
    if status.state == "ROLLED_BACK" and not (status.firmware_version==job.previous_version and
            status.image_sha256==job.previous_sha256):
        return []
    job.state = status.state
    job.last_sequence = status.sequence
    job.bytes_received = max(job.bytes_received,status.bytes_received)
    job.updated_at = utcnow()
    job.error = status.error
    job.installed_version = status.firmware_version
    job.installed_sha256 = status.image_sha256
    add_event(session,job,status.state,status.error,event_id=str(status.sequence),received=status.bytes_received)
    if status.state in {"CONFIRMED","ROLLED_BACK"}:
        device.firmware_version = status.firmware_version
    device.last_seen = utcnow()
    device.status = "ONLINE"
    session.add_all([job,device])
    session.commit()
    return [{"type":"ota.updated","data":{"device_id":device.id,"job_id":job.id,"state":job.state}}]

def download_token(job):
    return jwt.encode({"aud":"ota-download","sub":str(job.device_id),"job":job.id,"req":job.request_id,
        "exp":int(job.expires_at.replace(tzinfo=timezone.utc).timestamp())},settings.SECRET_KEY,algorithm="HS256")

def publish_request(code,payload):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(settings.MQTT_USERNAME,settings.MQTT_PASSWORD)
    try:
        client.connect(settings.MQTT_HOST,settings.MQTT_PORT,10)
        client.loop_start()
        result = client.publish(f"driver/{code}/ota/request",json.dumps(payload),qos=1,retain=False)
        result.wait_for_publish(timeout=5)
        return result.is_published()
    except (OSError,RuntimeError,ValueError): return False
    finally:
        client.disconnect()
        client.loop_stop()

def tick(engine,publisher=None):
    if not settings.OTA_ENABLED: return
    publisher = publisher or publish_request
    with Session(engine) as session:
        ids = session.exec(select(OtaJob.id).where(~OtaJob.state.in_(FINAL)).order_by(OtaJob.id).limit(100)).all()
    for identifier in ids:
        with Session(engine) as session:
            snapshot = session.get(OtaJob,identifier)
            # Always lock device before job, matching status ingestion and cancellation.
            device = session.exec(select(Device).where(Device.id==snapshot.device_id).with_for_update()).one()
            job = session.exec(select(OtaJob).where(OtaJob.id==identifier).with_for_update()).one()
            if job.state in FINAL or job.state == "RESULT_UNKNOWN": continue
            if job.expires_at <= utcnow():
                job.state = "FAILED" if job.state == "QUEUED" else "RESULT_UNKNOWN"
                job.error = "Hết hạn trước khi gửi" if job.state == "FAILED" else "Chưa nhận kết quả cuối; không tự gửi lại."
                job.updated_at = utcnow(); session.add(job); add_event(session,job,job.state,job.error); session.commit(); continue
            if job.state == "PUBLISHING" and (utcnow()-job.updated_at).total_seconds()>30:
                job.state="RESULT_UNKNOWN"; job.error="Backend dừng trong lúc gửi; không tự gửi lại."
                session.add(job);add_event(session,job,job.state,job.error);session.commit();continue
            if job.state != "QUEUED": continue
            artifact = session.get(FirmwareArtifact,session.get(OtaDeployment,job.deployment_id).artifact_id)
            reason = hardware_reason(device,artifact,"MAINTENANCE")
            if artifact.state != "RELEASED": reason = "Firmware đã bị thu hồi."
            try:
                if not reason: verify_artifact(artifact)
            except Exception: reason = "Firmware hoặc chữ ký không còn hợp lệ."
            if reason:
                job.state="REJECTED";job.error=reason;session.add(job);add_event(session,job,job.state,reason);session.commit();continue
            payload = {"protocol":"driver-ota-v1","device_code":device.device_code,"job_id":job.id,
                "request_id":job.request_id,"expires_at":int(job.expires_at.replace(tzinfo=timezone.utc).timestamp()),
                "manifest":artifact.manifest,"url":settings.OTA_PUBLIC_BASE_URL.rstrip('/')+f"{settings.API_STR}/ota/device/jobs/{job.id}/image",
                "download_token":download_token(job)}
            job.state="PUBLISHING";job.updated_at=utcnow();session.add(job);add_event(session,job,job.state);session.commit()
            success = publisher(device.device_code,payload)
            job = session.exec(select(OtaJob).where(OtaJob.id==identifier).with_for_update()
                .execution_options(populate_existing=True)).one()
            if job.state == "PUBLISHING":
                job.state="SENT" if success else "RESULT_UNKNOWN"
                job.error=None if success else "Broker chưa xác nhận gửi; kiểm tra thiết bị trước khi thử lại."
                job.updated_at=utcnow();session.add(job);add_event(session,job,job.state,job.error);session.commit()

def run_ota_tasks(stop):
    from app.core.db import engine
    while not stop.is_set():
        try: tick(engine)
        except Exception: logger.exception("OTA background task failed")
        stop.wait(1)

def guard_lifecycle(session,device):
    device=session.exec(select(Device).where(Device.id==device.id).with_for_update()
        .execution_options(populate_existing=True)).one()
    if session.exec(select(OtaJob.id).where(OtaJob.device_id==device.id,~OtaJob.state.in_(FINAL))).first():
        raise HTTPException(409,"Thiết bị còn đợt OTA chưa có kết quả cuối. Kiểm tra Firmware / OTA trước khi đổi trạng thái.")
    return device
