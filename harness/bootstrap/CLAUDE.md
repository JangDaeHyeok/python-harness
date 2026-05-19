# harness/bootstrap — harness-init 로컬 규칙

## 책임
- `initializer.py` — 외부 프로젝트에 하네스 규칙 파일을 한 번에 배치하는 부트스트래퍼.
- `templates.py` — ADR/컨벤션/구조/정책/CLAUDE.md/.claude 설정 템플릿.

## 대상 파일
- `docs/adr/0001-initial-architecture.md`
- `docs/code-convention.yaml`
- `harness_structure.yaml`
- `.harness/project-policy.yaml`
- `CLAUDE.md`
- `.claude/settings.json`, `.claude/hooks/*`, `.claude/skills/*` (스켈레톤)

## 로컬 규칙
- **타입별 LLM 응답 검증 필수.** YAML 대상은 YAML 파싱 + 필수 키 존재 검증, Markdown 대상은 최소 길이 검증.
- 검증 실패 또는 LLM 호출 실패 시 **내장 템플릿으로 폴백** (예외 전파 금지).
- 기존 파일은 기본적으로 보존한다. 덮어쓰려면 명시적으로 `--force`.
- 파일 쓰기는 `harness/tools/file_io.py`의 `atomic_write_text` 사용.
- 프로젝트 이름은 따옴표로 감싼 토큰을 우선 추출, 없으면 디렉터리명 정규화.

## 관련 ADR
- 0008 수정 모드와 프로젝트 정책 (정책 파일 구조), 0003 ADR 기반 아키텍처 규칙 (구조 YAML 형식).
