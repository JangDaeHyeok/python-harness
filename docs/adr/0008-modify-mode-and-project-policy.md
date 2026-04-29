# ADR-0008: 수정 모드(Modify Mode)와 프로젝트 정책 관리

- status: accepted
- date: 2026-04-29
- deciders: 하네스 팀

## 컨텍스트

기존 하네스는 새 프로젝트 생성(create) 중심으로 동작한다.
Planner가 전체 제품 스펙을 생성하고, Generator가 처음부터 코드를 작성하는 흐름이다.

그러나 실무에서는 기존 코드베이스를 수정하는 경우가 훨씬 많다.
기존 아키텍처, 코드 컨벤션, ADR, 테스트 결과 등의 컨텍스트를 수집하여
수정에 특화된 계획과 구현을 수행할 필요가 있다.

또한 프로젝트마다 서로 다른 정책(리뷰 언어, 필수 검사, 컨벤션 위치 등)을
관리할 수 있는 메커니즘이 필요하다.

## 결정

### 1. 수정 모드 (--mode modify)

`scripts/run_harness.py`에 `--mode create|modify` 옵션을 추가한다.

- `create` (기본값): 기존 동작과 동일하게 새 프로젝트를 생성한다.
- `modify`: 기존 코드베이스를 분석한 뒤 수정 작업을 수행한다.

modify 모드에서는:
1. `ModifyContextCollector`가 프로젝트 컨텍스트를 수집한다:
   - git branch, git diff, 변경된 파일 목록
   - 설계 의도 문서, 코드 컨벤션, ADR, 구조 규칙
   - 최근 테스트/검증 결과, 프로젝트 정책
2. 수정 전용 시스템 프롬프트가 에이전트에 적용된다.
3. Planner는 수정 계획을 ProductSpec 호환 형식으로 생성한다.
4. Generator는 기존 파일 수정에 집중한다.
5. Evaluator는 기존 기능 보존과 변경 정확성을 평가한다.

### 1-1. 수정 모드 체크포인트 재개

modify 모드의 기본 프로젝트 디렉터리는 현재 디렉터리다.
따라서 modify 실행이 중단된 뒤 사용자가 저장소 루트에서 자연스럽게
`python scripts/run_harness.py --resume` 또는 `--run-id <id>`를 실행하면
현재 디렉터리의 `.harness/checkpoints/`를 우선 확인한다.

- `--project-dir`이 명시되면 항상 그 값을 우선한다.
- `--mode modify`가 명시되면 현재 디렉터리를 기본 프로젝트 디렉터리로 사용한다.
- `--project-dir`이 없고 현재 디렉터리에 대상 체크포인트가 있으면 현재 디렉터리의 modify 실행으로 재개한다.
- 그 외 create 기본 실행은 기존처럼 `./project`를 사용한다.

### 2. 프로젝트 정책 파일 (.harness/project-policy.yaml)

프로젝트별 하네스 동작을 커스터마이즈하는 정책 파일을 도입한다.

- `ProjectPolicyManager`가 정책 파일을 관리한다.
- 정책 파일이 없으면 기본값을 사용한다 (하위 호환).
- `ModifyContextCollector`가 정책 파일을 컨텍스트에 포함한다.

### 3. 아키텍처 위치

- `ModifyContextCollector`: `harness/context/modify_context.py`
- `ProjectPolicyManager`: `harness/context/project_policy.py`
- 수정 모드 프롬프트: `harness/guides/prompts.py`
- 모드 분기: `HarnessConfig.mode` 필드, Orchestrator에서 분기

context 모듈의 기존 의존성 방향 규칙을 준수한다:
context → agents/sensors/review 의존 금지.

## 결과

### 긍정적
- 기존 코드베이스 수정 작업에 최적화된 흐름 제공
- 프로젝트별 정책 관리로 다양한 프로젝트에 적응 가능
- 기존 create 모드와 완전히 하위 호환
- 기존 3-에이전트 루프(Planner → Generator → Evaluator)를 재사용
- modify 실행 중단 후 `--resume`만으로 현재 저장소의 체크포인트를 자연스럽게 재개 가능

### 부정적
- 모드별 분기 로직이 Orchestrator에 추가됨
- 수정 모드 프롬프트를 별도로 유지보수해야 함
- CLI가 재개 시 현재 디렉터리 체크포인트 존재 여부를 확인하므로 project-dir 해석 규칙이 약간 복잡해짐

## 강제 규칙

- `harness_structure.yaml`에 필수 파일 규칙 추가
- context 모듈의 의존성 방향 규칙 유지 (ADR-0006)
