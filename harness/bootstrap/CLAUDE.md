# harness/bootstrap — harness-init 로컬 규칙

## 책임
- `initializer.py` — 외부 프로젝트에 하네스 규칙 파일을 한 번에 배치하는 부트스트래퍼.
- `templates.py` — ADR/컨벤션/구조/정책/CLAUDE.md/.claude 설정 + Python 골격(pyproject/gitignore/CI/smoke/package-init) 템플릿.
- `doctor.py` — GitHub/Python 사전 점검 로직(`run_doctor` → `DoctorCheck` 목록). print 금지, 출력은 `scripts/doctor.py`가 담당.

## 대상 파일

### 기본 타깃 (`ALL_TARGETS`)
- `docs/adr/0001-initial-architecture.md`
- `docs/code-convention.yaml`
- `harness_structure.yaml`
- `.harness/project-policy.yaml`
- `CLAUDE.md`
- `.claude/settings.json`, `.claude/hooks/post_session_checks.sh`
- `.claude/skills/*`는 배포하지 않는다. 외부 프로젝트에서 필요하면 수동 복사한다.

### 옵션 타깃 (`OPTIONAL_TARGETS`, opt-in)
- `.coderabbit.yaml` — `--with-coderabbit` 또는 `--only coderabbit`로만 활성. GitHub App 설치는 별도. `--with-coderabbit` 사용 시 `_sync_existing_policy_coderabbit_flag`가 기존 `.harness/project-policy.yaml`의 `review_tools.coderabbit` 플래그를 `true`로 자동 동기화한다(주석/다른 키 보존).
- Python 골격(`SCAFFOLD_TARGETS`): `pyproject.toml`, `<package_dir>/__init__.py`, `tests/test_smoke.py`, `.gitignore`, `.github/workflows/ci.yml`. `--scaffold` 또는 `--only pyproject,ci,...`로 활성. 기본 `ALL_TARGETS`에는 포함되지 않는다.

## src 레이아웃 / package_dir
- 패키지 위치는 `ProjectPolicy.source_root`(빈 값=flat, `src`=src 레이아웃)와 `package_dir` property로 표현한다. 템플릿/구조/마이그레이션 경로는 `package`가 아니라 `package_dir`를 쓴다.
- 마이그레이션 탐지(`PackageLocation`)는 루트와 `src/*/__init__.py`를 모두 후보로 모은다. 단일 후보면 `source_root`까지 정책에 기록하고, 루트·src 동시 존재 시 명시를 요구한다(자동 선택 금지). 상세는 ADR-0014.
- 정책이 `project.source_root`를 명시하면 `_resolve_migration_package`가 그 root만 탐색해 자동 탐지(루트 우선)보다 우선한다. 루트·src에 같은 패키지가 동시에 있어도 명시 정책대로 채택한다(`migrate_existing`이 `_read_policy_source_root` 결과를 전달).
- 비-migrate `run()`(scaffold/`--only package-init` 포함)도 기존 `.harness/project-policy.yaml`의 `project.package`/`project.source_root`를 읽어(`_read_policy_package`/`_read_policy_source_root`) 컨텍스트에 반영한다. 정책이 없으면 디렉터리명에서 파생(flat). 따라서 기존 src 레이아웃에 scaffold하면 `src/<policy.package>/__init__.py`에 쓴다.

## 로컬 규칙
- **타입별 LLM 응답 검증 필수.** YAML 대상은 YAML 파싱 + 필수 키 존재 검증, Markdown 대상은 최소 길이 검증.
- 검증 실패 또는 LLM 호출 실패 시 **내장 템플릿으로 폴백** (예외 전파 금지).
- 기존 파일은 기본적으로 보존한다. 덮어쓰려면 명시적으로 `--force`.
- 모든 쓰기 대상 경로(PACKAGE_INIT 등 정책 `source_root`/`package`에서 파생되는 동적 경로 포함)는 `_apply_plans`에서 `shell.validate_path`로 프로젝트 디렉터리 봉쇄를 검증한 뒤 쓴다. 정책 입력의 `..`·절대경로는 거부한다.
- 파일 쓰기는 `harness/tools/file_io.py`의 `atomic_write_text` 사용.
- 프로젝트 이름은 따옴표로 감싼 토큰을 우선 추출, 없으면 디렉터리명 정규화.
- 정책 파일 플래그(예: `review_tools.coderabbit`) 동기화는 라인 단위 정규식(`_apply_coderabbit_flag`)으로 처리해 템플릿 주석을 보존한다. YAML round-trip은 주석 손실이 있어 사용하지 않는다.

## 관련 ADR
- 0008 수정 모드와 프로젝트 정책 (정책 파일 구조), 0003 ADR 기반 아키텍처 규칙 (구조 YAML 형식), 0010 고정 구조 강제, 0011 마이그레이션 모드, 0014 src 레이아웃과 source_root.
