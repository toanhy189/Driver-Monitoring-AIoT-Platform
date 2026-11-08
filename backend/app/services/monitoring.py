"""Bounded process metrics plus durable database counts; no user/video labels."""
from collections import deque
from threading import Lock
from datetime import datetime, timezone
from sqlmodel import Session, select
from sqlalchemy import func
from app.core.db import engine
from app.models.device import Device
from app.models.alert import Alert
from app.models.command import Command

_lock = Lock()
_http = {}
_http_ms = deque(maxlen=512)
_mqtt_connections = 0


def record_request(method, status, milliseconds):
    with _lock:
        key = (method if method in {"GET","POST","PUT","PATCH","DELETE","OPTIONS"} else "OTHER", int(status)//100)
        _http[key] = _http.get(key,0)+1
        _http_ms.append(milliseconds)


def record_mqtt_connection():
    global _mqtt_connections
    with _lock: _mqtt_connections += 1


def render():
    with Session(engine) as session:
        online=session.exec(select(func.count()).select_from(Device).where(Device.status=="ONLINE", Device.lifecycle_state!="DECOMMISSIONED")).one()
        alerts=session.exec(select(func.count()).select_from(Alert)).one()
        commands=session.exec(select(func.count()).select_from(Command)).one()
        completed=session.exec(select(Command).where(Command.completed_ack_at.is_not(None))
            .order_by(Command.completed_ack_at.desc()).limit(200)).all()
        latency=sorted((row.completed_ack_at-row.created_at).total_seconds()*1000 for row in completed
                       if row.created_at and row.completed_ack_at>=row.created_at)
    with _lock:
        requests=dict(_http); durations=sorted(_http_ms); reconnects=max(0,_mqtt_connections-1)
    lines=["# TYPE devices_online gauge",f"devices_online {online}",
           "# TYPE alerts_total gauge",f"alerts_total {alerts}",
           "# TYPE commands_total gauge",f"commands_total {commands}",
           "# TYPE mqtt_reconnect_total counter",f"mqtt_reconnect_total {reconnects}"]
    for (method,status),count in requests.items():
        lines.append(f'http_requests_total{{method="{method}",status_class="{status}xx"}} {count}')
    for name,values in (("http_request_latency_ms",durations),("command_ack_latency_ms",latency)):
        for q in (.5,.95):
            if values: lines.append(f'{name}{{quantile="{q}"}} {values[min(len(values)-1,int((len(values)-1)*q))]}')
        lines.append(f"{name}_samples {len(values)}")
    return "\n".join(lines)+"\n"
