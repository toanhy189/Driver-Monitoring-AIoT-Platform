from fastapi import HTTPException


OUTPUTS = ("led", "buzzer", "motor")
LEVELS = ("1", "2", "3")


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
                if type(duration) is not int or not 0 <= duration <= 10000:
                    raise HTTPException(
                        status_code=422,
                        detail=f"{output} level {level} {field} must be 0-10000 ms",
                    )
                result[output][level][field] = duration
    return result
