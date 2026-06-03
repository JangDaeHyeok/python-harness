# ADR-0014: src 레이아웃 지원과 project.source_root

- **상태**: Accepted
- **날짜**: 2026-06-03
- **관련 ADR**: ADR-0008, ADR-0010, ADR-0011

## 배경

ADR-0010은 외부 Python 프로젝트에 고정 구조를 강제하고, ADR-0011은 기존 프로젝트를 그 구조로 보강하는 마이그레이션 모드를 정의한다.
그러나 두 결정은 패키지가 항상 저장소 루트(`<package>/__init__.py`)에 있다고 가정했고, `harness-init --migrate`와 구조 게이트는 `src/<package>/__init__.py` 같은 src 레이아웃을 명시적으로 거부했다.
src 레이아웃은 패키징·테스트 격리 측면에서 널리 쓰이는 표준 배치이므로, 이를 거부하면 다수의 실제 Python 프로젝트에 하네스를 적용할 수 없다.

## 결정

패키지 위치를 단일 변수로 표현하는 정책 필드 `project.source_root`를 도입한다.

- `ProjectPolicy.source_root: str` — 빈 문자열은 flat 루트, `"src"`는 src 레이아웃을 의미한다.
- `ProjectPolicy.package_dir` property가 `source_root`와 `package`를 합쳐 루트 기준 상대 경로(`src/<package>` 또는 `<package>`)를 반환한다.
- 구조 게이트, Phase `allowed_files`/검증 명령, modify 컨텍스트, 부트스트랩 템플릿은 모두 `package_dir`를 단일 진입점으로 재사용한다.
- `harness-init --migrate`는 루트와 `src/*`를 모두 탐지해 단일 후보면 자동 채택하고 `source_root`를 정책에 기록한다. 루트와 src에 후보가 동시에 존재하면 기존 정책대로 명시를 요구한다(자동 선택 금지).
- 정책이 `project.source_root`를 명시한 경우, 마이그레이션은 그 root만 탐색해 자동 탐지보다 우선한다. 따라서 루트·src에 같은 패키지가 함께 있어도 명시한 `source_root`가 유지되며 루트 우선 탐색으로 덮어쓰이지 않는다.

ADR-0010의 고정 구조 원칙은 유지한다. 패키지의 "위치"만 변수 1개로 일반화할 뿐, 그 외 규칙(필수 파일, 금지 패턴, 의존 방향)은 그대로다.

## 대안

- src 레이아웃을 계속 거부한다: 표준 배치의 실제 프로젝트를 배제하므로 채택하지 않는다.
- 레이아웃별로 구조 게이트/템플릿/Phase 로직을 분기한다: 동일 개념이 여러 지점에 흩어져 회귀 위험이 커지므로 채택하지 않는다.
- 패키지 경로를 호출 지점마다 재계산한다: `package_dir` 단일 property로 수렴하는 편이 일관적이라 채택하지 않는다.

## 결과

- 긍정적 결과: flat·src 두 레이아웃을 동일 코드 경로로 처리하며, flat(`source_root=""`)에서 기존 동작이 변하지 않는다.
- 긍정적 결과: 패키지 위치 관련 로직이 `package_dir` 한 곳으로 모여 향후 레이아웃 확장 시 변경 지점이 좁다.
- 트레이드오프: `source_root`가 정책/구조 게이트/Phase/템플릿의 여러 지점을 건드리므로, 두 레이아웃 모두에 대한 회귀 테스트를 고정해야 한다.

## 검증 방법

- `tests/test_project_policy.py`에서 `source_root` 직렬화/역직렬화와 `package_dir` 계산을 검증한다.
- `tests/test_structure_gate.py`, `tests/test_phase_manager.py`에서 src 레이아웃 경로가 반영되는지 확인한다.
- `tests/test_bootstrap_migrate.py`에서 `src/<package>` 마이그레이션 성공과 `source_root: src` 기록을 검증한다.
- `ruff check .`, `mypy harness`, `python3 scripts/check_structure.py`, `pytest`가 모두 통과해야 한다.
