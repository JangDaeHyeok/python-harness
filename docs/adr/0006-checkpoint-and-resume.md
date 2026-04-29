---
status: accepted
date: 2026-04-28
enforced_by:
  - required_files
---

# ADR-0006: 체크포인트와 중단 후 재시작

## Context

하네스 실행은 수십 분~수 시간 걸릴 수 있으며, 네트워크 장애·사용자 중단·프로세스 크래시 시
전체 실행을 처음부터 재시작해야 한다. 이미 통과한 스프린트를 다시 실행하면
비용과 시간이 낭비된다.

## Decision

`harness/context/checkpoint.py`에 체크포인트 저장/복원 기능을 구현한다:

1. **데이터 모델** — `SessionState`, `SprintState`, `AttemptState`
   - 실행 단계를 `Phase` enum으로 추적 (init → planning_done → sprint/attempt → run_done)
   - 스프린트별 시도 횟수, 통과 여부, 점수를 기록

2. **CheckpointStore**
   - `.harness/checkpoints/{run_id}.json`에 저장
   - `latest.json` 포인터로 가장 최근 실행 추적
   - atomic write (tempfile + os.replace)로 파일 손상 방지

3. **Orchestrator 연동** — 7개 시점에서 체크포인트 저장:
   - planning_done, sprint_start, attempt_start, impl_done, eval_done, sprint_done, run_done

4. **재개 방식**
   - `--run-id {id}` 또는 `--resume` (latest) CLI 옵션
   - 이미 완료된 스프린트는 건너뛰고, 중단된 스프린트부터 재시작

## Consequences

- 장시간 실행 중 중단돼도 완료된 작업을 보존할 수 있다
- `.harness/checkpoints/` 디렉터리에 체크포인트 파일이 누적된다
- context 모듈은 agents, sensors, review에 의존하지 않는다 (단방향)
