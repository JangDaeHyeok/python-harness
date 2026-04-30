"""파일 I/O 보조 함수."""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    prefix: str = ".atomic-",
) -> None:
    """텍스트 파일을 임시 파일에 쓴 뒤 원자적으로 교체한다."""
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
        prefix=prefix,
    )
    closed = False
    try:
        os.write(fd, content.encode(encoding))
        os.fsync(fd)
        os.close(fd)
        closed = True
        os.replace(tmp_path, str(path))
    except BaseException:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
