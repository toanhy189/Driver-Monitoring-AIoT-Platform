"""Bounded chart summaries; the original telemetry and history API stay intact."""
import math

from sqlalchemy import Float, case, cast, func
from sqlmodel import select

from app.services.time_utils import as_utc


def chart_summary(session, query, limit=200):
    t = query.subquery()
    total, first, last = session.exec(select(func.count(), func.min(t.c.recorded_at),
        func.max(t.c.recorded_at)).select_from(t)).one()
    if not total:
        return {"chart_points": [], "timeline_segments": [], "total_samples": 0,
                "bucket_seconds": 0, "chart_mode": "RAW"}
    bucket_seconds = max(1, math.ceil((last - first).total_seconds() / max(1, limit - 1))) if total > limit else 0
    if bucket_seconds:
        t = select(t, func.lag(t.c.recorded_at).over(order_by=[t.c.recorded_at, t.c.id])
            .label("previous_recorded_at")).subquery()
    mar = cast(t.c.ai_signals["mar"].as_string(), Float)
    measured = [case((t.c.face_detected.is_not(False), value), else_=None)
                for value in (t.c.ear, t.c.perclos, mar)]
    if bucket_seconds:
        bucket = func.floor(func.extract("epoch", t.c.recorded_at - first) / bucket_seconds)
        gap = case((func.extract("epoch", t.c.recorded_at - t.c.previous_recorded_at) > 5, 1), else_=0)
        fields = [func.min(t.c.recorded_at), func.max(t.c.recorded_at), func.count(), func.max(gap)]
        for value in measured:
            fields.extend([func.avg(value), func.min(value), func.max(value), func.count(value) < func.count()])
        rows = session.exec(select(*fields).select_from(t).group_by(bucket).order_by(bucket)).all()
        points = []
        for index, row in enumerate(rows):
            point = {"id": f"bucket-{index}", "recorded_at": as_utc(row[0]),
                     "end_at": as_utc(row[1]), "samples": row[2]}
            for offset, name in enumerate(("ear", "perclos", "mar")):
                mean, low, high, missing = row[4 + offset * 4:8 + offset * 4]
                point.update({name: mean, name + "_min": low, name + "_max": high,
                              name + "_has_gap": bool(row[3] or missing)})
            points.append(point)
    else:
        rows = session.exec(select(t.c.id, t.c.recorded_at, *measured)
            .order_by(t.c.recorded_at, t.c.id)).all()
        points = [{"id": row[0], "recorded_at": as_utc(row[1]),
                   "ear": row[2], "perclos": row[3], "mar": row[4]} for row in rows]
    # Group consecutive states across the full window, breaking at observation gaps.
    state = case((t.c.face_detected.is_(False), "UNKNOWN"), else_=func.coalesce(t.c.driver_state, "UNKNOWN"))
    order = [t.c.recorded_at, t.c.id]
    sequence = select(t.c.id, t.c.recorded_at, state.label("state"),
        func.lag(state).over(order_by=order).label("previous_state"),
        func.lag(t.c.recorded_at).over(order_by=order).label("previous_time")).subquery()
    changed = case(((sequence.c.state == sequence.c.previous_state)
        & (func.extract("epoch", sequence.c.recorded_at - sequence.c.previous_time) <= 5), 0), else_=1)
    grouped = select(sequence.c.recorded_at, sequence.c.state, func.sum(changed).over(
        order_by=[sequence.c.recorded_at, sequence.c.id]).label("segment")).subquery()
    segments = session.exec(select(grouped.c.state, func.min(grouped.c.recorded_at),
        func.max(grouped.c.recorded_at), func.count()).group_by(grouped.c.segment, grouped.c.state)
        .order_by(func.max(grouped.c.recorded_at).desc()).limit(60)).all()
    return {"total_samples": total, "chart_points": points,
            "bucket_seconds": bucket_seconds, "chart_mode": "BUCKETED" if bucket_seconds else "RAW",
            "timeline_segments": [{"driver_state": row[0], "start": as_utc(row[1]),
                "end": as_utc(row[2]), "samples": row[3]} for row in reversed(segments)]}
