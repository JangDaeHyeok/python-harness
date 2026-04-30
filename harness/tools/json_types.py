"""JSON 역직렬화 타입 변환 헬퍼."""

from __future__ import annotations


def coerce_int(value: object, default: int = 0) -> int:
    """JSON 값에서 int를 안전하게 추출한다."""
    parsed = coerce_optional_int(value)
    return parsed if parsed is not None else default


def coerce_optional_int(value: object) -> int | None:
    """JSON 값이 유효한 int이면 반환하고 아니면 None을 반환한다."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def coerce_float(value: object, default: float = 0.0) -> float:
    """JSON 값에서 float를 안전하게 추출한다."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def coerce_int_list(value: object) -> list[int]:
    """JSON 배열에서 int 목록을 안전하게 추출한다."""
    if not isinstance(value, list):
        return []
    return [
        parsed
        for item in value
        if (parsed := coerce_optional_int(item)) is not None
    ]
