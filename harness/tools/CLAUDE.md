# harness/tools — 유틸리티 로컬 규칙

## 책임
- `shell.py` — 셸 명령 안전 래퍼(`run_command_safe`, `validate_command`), 경로 봉쇄 검증(`validate_path`/정규화 경로를 반환하는 `resolve_safe_path`), HTTP 요청 URL 검증(`validate_http_url`: 스킴 allowlist·link-local 차단), git 커밋 전용 안전 래퍼(`run_git_commit_safe`: 타임아웃 강제, mutating git을 이 한 곳으로 집중). (ADR-0016)
- `path_safety.py` — 식별자 정규화/검증(`sanitize_branch_name`, `validate_run_id`).
- `file_io.py` — 원자적 파일 쓰기(`atomic_write_text`).
- `api_client.py` — LLM 엔드포인트 호출(`HarnessClient`).
- `adr.py` — ADR 로더.
- `json_types.py` — 공용 JSON 타입.

## 로컬 규칙 (CRITICAL)
- **셸 명령은 절대 `subprocess.run`/`os.system`을 직접 사용하지 않는다.** 반드시 `run_command_safe`를 거친다.
- **파일 경로 입력**은 `shell.py`의 `validate_path`로 검증한 뒤 사용. 사용자/LLM/정책 파일에서 오는 경로는 검증 없이 신뢰하지 않는다.
- 파일 쓰기는 `atomic_write_text`로 원자적으로 수행한다 (임시 파일 → `os.replace`).
- `tools/`는 다른 어떤 패키지에도 의존하지 않는 leaf 계층이다. 역방향 import 금지.
- LLM 응답 파싱 실패 시 안전 기본값 반환 (예외 전파 금지).

## 관련 ADR
- 0001~0013 전반에 걸쳐 인프라 계층으로 인용된다. 0016 보안·견고성 하드닝(SSRF/경로/커밋 래퍼).
