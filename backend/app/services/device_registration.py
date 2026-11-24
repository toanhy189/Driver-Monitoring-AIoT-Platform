"""Remove only unused registrations; operational records are retained by decommissioning."""
from sqlalchemy import or_
from sqlmodel import select
from app.models.ai_event import AiEvent, AiMessageReceipt, RuleBinding, RuleRuntime
from app.models.alert import Alert
from app.models.command import Command
from app.models.config import Config
from app.models.telemetry import Telemetry
from app.models.user_device import UserDevice
from app.models.video import AiVideo


def deletion_block_reason(session, device, admin_id):
    if device.lifecycle_state != "REGISTERED":
        return "Chỉ xóa đăng ký mới chưa cấp kết nối. Thiết bị đã vận hành dùng Ngừng sử dụng."
    if device.mqtt_username or device.mqtt_password or device.last_seen or device.firmware_version or device.status != "OFFLINE":
        return "Thiết bị đã có thông tin kết nối hoặc dấu hiệu hoạt động; hãy dùng Ngừng sử dụng."
    assigned = select(UserDevice.id).where(UserDevice.device_id == device.id,
        or_(UserDevice.user_id != admin_id, UserDevice.unassigned_at.is_not(None))).limit(1)
    if session.exec(assigned).first() is not None:
        return "Thiết bị đã được phân công hoặc có lịch sử phân công; hãy dùng Ngừng sử dụng."
    references = [(Telemetry, Telemetry.device_id), (AiEvent, AiEvent.device_id),
        (AiMessageReceipt, AiMessageReceipt.device_id), (Alert, Alert.device_id),
        (Command, Command.device_id), (Config, Config.device_id), (AiVideo, AiVideo.device_id),
        (RuleRuntime, RuleRuntime.source_device_id)]
    for model, column in references:
        if session.exec(select(column).where(column == device.id).limit(1)).first() is not None:
            return "Thiết bị đã có dữ liệu hoặc cấu hình; hãy dùng Ngừng sử dụng để giữ lịch sử."
    binding = select(RuleBinding.source_device_id).where(or_(RuleBinding.source_device_id == device.id,
        RuleBinding.target_device_id == device.id)).limit(1)
    if session.exec(binding).first() is not None:
        return "Thiết bị đã có liên kết cảnh báo; hãy dùng Ngừng sử dụng."
    return None
