---
status: accepted
date: 2026-04-28
enforced_by:
  - required_files
  - review_dependency_direction
---

# ADR-0004: 리뷰 산출물 워크플로 도입

## Context

코드 리뷰·스프린트 평가 결과가 하네스 실행마다 사라지거나 산재되어 있어
- 설계 결정의 근거를 추적하기 어렵고
- PR 본문 작성이 수동으로 이루어지며
- 리뷰 코멘트 반영 여부를 검증할 수 없었다.

팀은 `.harness/artifacts/` 에 스프린트 산출물을 저장하고 있었으나
리뷰 특화 산출물(설계 의도, 평가 기준, PR 본문, 반영 판단 로그)을 위한
별도 구조가 없었다.

## Decision

`harness/review/` 패키지를 신설하고 7가지 기능을 구현한다:

1. **artifacts.py** (`ReviewArtifactManager`): 브랜치별 리뷰 산출물을
   `.harness/review-artifacts/{branch}/` 에 저장·조회한다.

2. **conventions.py** (`ConventionLoader`): `docs/code-convention.yaml`을
   로드하여 카테고리·태그 기반 필터링을 제공한다.

3. **criteria.py** (`CriteriaGenerator`): ADR과 컨벤션에서 평가 기준을
   결정적 로직(LLM 불필요)으로 생성한다. ADR 로딩은 `harness/tools/adr.py`의
   `ADRLoader`가 담당한다.

4. **intent.py** (`IntentGenerator`): 스프린트 정보에서 `design-intent.md`를
   구조화된 형식으로 생성한다.

5. **pr_body.py** (`PRBodyGenerator`): git diff와 산출물을 기반으로
   `pr-body.md`를 자동 생성한다.

6. **reflection.py** (`ReviewReflection`): 리뷰 코멘트별 ACCEPT/REJECT/DEFER를
   판정하고 `review-comments.md`에 기록한다. severity → [p1~p4] 우선순위 매핑.

7. **worktree.py** (`WorktreeManager`): detached HEAD worktree에서 격리 실행하고
   산출물을 delta sync로 보존한다. dirty worktree면 중단하고, 생성 실패 시 예외를
   발생시킨다 (원본 디렉터리 fallback 금지). Orchestrator의 worktree 동기화는
   파일 추가·수정·삭제를 반영하되, 메인 프로젝트의 같은 경로에 로컬 변경이 있으면
   충돌로 보고 중단한다.

### 아키텍처 원칙

- `harness/review/` 는 `harness/tools/` 와 `harness/sensors/` 에만 의존한다.
- `harness/agents/` 는 `harness/review/` 를 import하는 방향(agents → review)은 허용한다.
- `harness/review/` 가 `harness/agents/` 를 import하는 방향(review → agents)은 피한다.
- LLM 호출보다 결정적 로직을 우선한다 (ADR-0002 연장).

## Consequences

- **긍정**: 설계 의도·평가 기준이 파일로 남아 리뷰·감사 가능
- **긍정**: PR 본문 작성 자동화로 반복 수작업 제거
- **긍정**: 리뷰 반영 판단이 추적 가능해져 QA 루프 강화
- **긍정**: worktree 격리와 충돌 감지로 실험적 산출물이 작업 트리를 오염시키지 않음
- **부정**: `.harness/review-artifacts/` 디렉터리가 `.gitignore` 관리 대상 추가 필요
- **중립**: worktree 생성에 git 저장소가 필요하며, 없으면 WorktreeError를 발생시킨다
