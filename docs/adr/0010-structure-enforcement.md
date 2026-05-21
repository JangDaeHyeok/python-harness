# ADR-0010: 외부 프로젝트 고정 구조 강제

- **상태**: Accepted
- **날짜**: 2026-05-20
- **관련 ADR**: ADR-0008, ADR-0009

## 배경

본 하네스는 외부 Python 프로젝트에 적용되는 AI 코딩 게이트다.
지금까지 modify 모드와 프로젝트 정책은 다양한 프로젝트 컨텍스트를 수집할 수 있도록 설계되었지만,
외부 프로젝트마다 디렉터리 구조, 테스트 명령, 문서 위치를 유연하게 허용하면 Planner, Generator, Evaluator가 매번 다른 전제를 갖게 된다.
하네스가 평가 신뢰성과 LLM 출력 일관성을 보장하려면 입력 프로젝트의 구조가 결정적이어야 한다.

## 결정

외부 Python 프로젝트가 본 하네스를 사용하려면 다음 고정 구조를 따른다.

- `docs/`
- `docs/adr/`
- `docs/code-convention.yaml`
- `harness_structure.yaml`
- `.harness/project-policy.yaml`
- `tests/`
- `scripts/`
- 정책의 `package` 필드가 가리키는 Python 패키지 디렉터리

구조에서 허용하는 변수는 `.harness/project-policy.yaml`의 `package` 필드 1개뿐이다.
이 필드는 본 저장소의 `harness/`에 해당하는 외부 프로젝트 패키지명을 지정한다.

필수 구조를 만족하지 못하면 하네스 실행을 거부한다.
오류 메시지는 무엇이 누락됐는지, 왜 필요한지, 어떻게 고치는지를 한국어 3줄로 명시하고 `harness-init --migrate` 실행을 안내한다.
이 구조 강제를 우회하는 플래그는 만들지 않는다.

## 대안

- `project-policy.yaml`에 `commands` 섹션을 추가하여 테스트, 타입 검사, 린트, 구조 검사 명령을 프로젝트별로 유연하게 지정하는 방안을 검토했다.
  이 방식은 프로젝트별 진입 장벽을 낮추지만, Evaluator와 Phase Worker가 같은 산출물을 같은 의미로 해석한다는 보장을 약화시킨다.
  또한 LLM이 문서와 정책을 읽을 때 매번 다른 명령 체계와 경로 규칙을 추론해야 하므로 출력 일관성이 떨어진다.
- 다중 레이아웃을 지원하여 `src/`, 단일 패키지 루트, 모노레포 하위 패키지 등을 자동 탐지하는 방안을 검토했다.
  이 방식은 초기 적용 범위는 넓히지만, 실패 원인이 프로젝트 구조인지 생성 코드인지 분리하기 어렵게 만든다.
  하네스가 게이트로 기능해야 하는 목적과 맞지 않아 채택하지 않는다.

## 결과

- 긍정적 결과: Planner, Generator, Evaluator, Phase Worker가 항상 같은 프로젝트 구조를 전제로 동작한다.
- 긍정적 결과: docs-diff, ADR 로딩, 구조 검사, 테스트 실행, PR 자동화 산출물 위치가 결정적이 된다.
- 부정적 결과 / 트레이드오프: 기존 Python 프로젝트는 하네스 적용 전에 `harness-init --migrate`로 구조를 맞춰야 한다.
- 후속 조치: P0~P4 변경에서 파이프라인, `phase_manager`, 부트스트랩, orchestrator는 이 ADR을 근거로 구조 검사를 실행 전 게이트로 추가한다.
- 후속 조치: `harness-init --migrate`는 누락된 고정 구조를 생성하거나 이동 가이드를 제공해야 한다.

## 검증 방법

하네스 실행 초기에 프로젝트 루트의 필수 경로를 검사한다.
`.harness/project-policy.yaml`을 파싱하여 `package` 필드를 읽고, 해당 패키지 디렉터리가 존재하는지 확인한다.
필수 경로 또는 패키지 디렉터리가 없으면 실행을 중단하고 한국어 3줄 오류와 `harness-init --migrate` 안내를 출력한다.

자동 검증은 다음 항목으로 구성한다.

- 구조 게이트 단위 테스트: 필수 경로 누락 시 실행 거부와 메시지 형식을 검증한다.
- 정책 파싱 테스트: `package` 필드 누락 또는 잘못된 값일 때 안전하게 실패하는지 검증한다.
- 통합 검증: `ruff check .`, `mypy harness`, `python3 scripts/check_structure.py`, `pytest`가 모두 통과해야 한다.
