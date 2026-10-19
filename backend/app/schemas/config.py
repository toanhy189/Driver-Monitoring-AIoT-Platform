from fastapi import HTTPException


OUTPUTS = ("led", "buzzer", "motor")
LEVELS = ("1", "2", "3")
TIMING_RANGES = {"on_ms": (50, 5000), "off_ms": (50, 10000)}


def validate_timings(value: object) -> dict:
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="timings must be an object")
    result = {}
    for output in OUTPUTS:
        profile = value.get(output)
        if not isinstance(profile, dict):
            raise HTTPException(status_code=422, detail=f"Missing {output} timings")
        result[output] = {}
        for level in LEVELS:
            pair = profile.get(level)
            if not isinstance(pair, dict):
                raise HTTPException(status_code=422, detail=f"Missing {output} level {level}")
            result[output][level] = {}
            for field in ("on_ms", "off_ms"):
                duration = pair.get(field)
                minimum, maximum = TIMING_RANGES[field]
                if type(duration) is not int or not minimum <= duration <= maximum:
                    raise HTTPException(
                        status_code=422,
                        detail=f"{output} level {level} {field} must be {minimum}-{maximum} ms",
                    )
                result[output][level][field] = duration
    return result
