# ADR-0016: 보안·견고성 하드닝

- **상태**: Accepted
- **날짜**: 2026-07-02
- **관련 ADR**: ADR-0001, ADR-0002, ADR-0008
- **태그**: security, ssrf, path-safety, fallback, subprocess, sensors
- **영향 경로**: harness/tools/shell.py, harness/agents/generator.py, harness/agents/evaluator.py, harness/agents/planner.py, harness/sensors/computational/structure_test.py

## 배경

코드베이스 분석 결과, 품질 게이트(ruff/mypy/pytest/구조 규칙)는 모두 통과하지만
프로젝트가 스스로 CRITICAL로 명시한 규칙을 코드가 어기는 지점이 다섯 군데 확인됐다.

- `EvaluatorAgent._check_url`이 LLM(tool_use)이 지정한 임의 URL로 요청을 보내며, 스킴·호스트 검증이 없어 `file://` 로컬 파일 읽기나 클라우드 메타데이터(`169.254.169.254`) 접근이 가능했다(SSRF). 반면 정상 용례상 로컬 앱 평가(기본 `http://localhost:3000`)는 유지되어야 한다.
- `validate_path`가 `.resolve()`로 검증하지만, 호출부(generator/evaluator)는 비정규화 경로(`self.project_dir / path`)를 다시 조립해 사용했다. 검증 시점과 사용 시점이 달라 심볼릭 링크 봉쇄가 defense-in-depth 관점에서 약했다.
- `PlannerAgent.process_response`가 JSON 파싱 실패 시 `ValueError`를 전파해, "LLM 파싱 실패 시 안전 기본값 폴백" 규칙을 위반하고 전체 실행을 중단시켰다. `from_dict`도 필수 키를 직접 인덱싱해 `KeyError`를 전파했다.
- `GeneratorAgent._git_commit`이 `run_command_safe`를 우회해 `subprocess.run`을 직접 호출하고 타임아웃도 없었다("셸은 반드시 shell.py 경유" 위반).
- `StructureAnalyzer.__init__`이 생성자에서 파일 IO(`_load_config`/`_load_adrs`)를 수행해 "`__init__`에서 부수 효과 금지" 규칙의 유일한 위반이었다.

## 결정

다섯 항목을 tools 계층 중심으로 하드닝한다.

1. **HTTP 요청 스킴 allowlist + link-local 차단** (`harness/tools/shell.py`의 `validate_http_url`)
   - 스킴을 `http`/`https`로 제한해 `file://` 등 비-HTTP 스킴을 차단한다.
   - IP 리터럴 호스트가 link-local 대역(`169.254.0.0/16`, `fe80::/10`)이면 차단한다. localhost·사설 대역은 로컬 앱 평가 정상 용례이므로 허용한다.
   - `EvaluatorAgent._check_url`은 요청 전 이 함수로 검증한다.

2. **정규화된 안전 경로 반환** (`harness/tools/shell.py`의 `resolve_safe_path`)
   - 프로젝트 봉쇄를 검증한 뒤 검증에 사용한 정규화 경로(`Path`)를 그대로 반환한다. `validate_path`는 이 함수 위의 얇은 래퍼로 유지해 하위 호환한다.
   - generator/evaluator의 파일 읽기·쓰기는 반환된 정규화 경로를 사용해 검증-사용 불일치를 없앤다. `GeneratorAgent._write_file`은 `atomic_write_text`로 원자적 쓰기를 수행한다.

3. **Planner 파싱 폴백** (`harness/agents/planner.py`)
   - `process_response`는 파싱 실패·비객체 응답 시 예외를 전파하지 않고 `ProductSpec.empty(...)`(스프린트 없음)를 반환한다. `from_dict`는 `.get` 기반으로 필수 키 누락을 허용한다.

4. **git commit 전용 안전 래퍼** (`harness/tools/shell.py`의 `run_git_commit_safe`)
   - `git add`/`git commit`은 mutating 작업이라 일반 allowlist에서 계속 차단하되, 스프린트 커밋이라는 정상 용례를 위해 tools 계층에서만 노출하는 전용 래퍼로 타임아웃을 강제하고 subprocess 사용을 이 한 곳으로 집중한다. `GeneratorAgent._git_commit`은 이 래퍼를 호출한다.

5. **StructureAnalyzer 지연 로드** (`harness/sensors/computational/structure_test.py`)
   - `__init__`은 경로만 보관하고, `rules`/`adrs`는 첫 접근 시 로드하는 property로 전환해 부수 효과를 제거한다.

## 대안

- **localhost까지 전면 차단(엄격 SSRF)**: 평가 대상 앱이 로컬에서 뜨는 핵심 용례를 깨뜨려 기각. 스킴 allowlist + 메타데이터 대역 차단으로 실질 위험을 제거하는 선에서 절충.
- **`validate_path` 시그니처를 `(Path, str)`로 변경**: 모든 호출부를 동시에 고쳐야 하고 하위 호환이 깨져 기각. 신규 `resolve_safe_path`를 추가하고 `validate_path`는 래퍼로 유지.
- **`git commit`을 일반 allowlist에 편입**: LLM이 임의 시점에 커밋할 수 있게 되어 mutating 작업 차단 정책과 충돌. 전용 감사 래퍼로 한정.

## 결과

- 긍정: LLM이 제어하는 URL/경로/커밋 경로의 공격 표면이 축소되고, 파싱 실패가 실행을 중단시키지 않는다. subprocess 직접 호출이 tools 계층으로 수렴한다.
- 트레이드오프: `run_git_commit_safe`는 여전히 subprocess를 직접 쓰지만, 이는 tools 계층에 의도적으로 국한한 유일한 mutating git 경로다. link-local 차단은 IP 리터럴만 대상으로 하며 DNS 리바인딩은 범위 밖(로컬 평가 특성상 위험 낮음).
- 후속: `orchestrator.py`/`auto_pr_pipeline.py`의 읽기 전용 git 직접 호출은 별도 ADR에서 다룰 수 있다.

## 검증 방법

- `tests/test_shell.py`: `resolve_safe_path`(정규화/탈출/심볼릭 링크), `validate_http_url`(로컬 허용/비-HTTP 차단/link-local 차단), `run_git_commit_safe`(커밋 성공/디렉터리 부재), 일반 셸 경로의 `git commit` 차단 유지.
- `tests/test_agents.py`: Planner 파싱 폴백·`from_dict` 관대 파싱, Generator 쓰기/심볼릭 링크 차단, Evaluator SSRF 스킴·메타데이터 차단·심볼릭 링크 읽기 차단·criteria 키 누락 폴백.
- `tests/test_structure.py`: `__init__` 무부수효과(지연 로드) 및 설정 부재 시 빈 결과.
- 회귀: `ruff check . && mypy harness && python3 scripts/check_structure.py && pytest`.
