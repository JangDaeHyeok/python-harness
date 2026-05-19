---
name: phase-handoff
description: Produce the 20-line-or-less handoff summary that each headless Phase leaves for the next Phase under .harness/tasks/sprint-{N}/{phase_id}-handoff.md. Use whenever finishing a phase in `--use-headless-phases` execution.
---

# Phase 핸드오프 작성 가이드

## 언제 트리거되는가
- 헤드리스 Phase 실행(`--use-headless-phases`) 중 한 Phase를 완료하고 다음 Phase로 넘어갈 때.
- `.harness/tasks/sprint-{N}/{phase_id}-handoff.md` 파일을 생성·갱신해야 할 때.
- Phase 재시도/재개 시 이전 Phase의 핸드오프를 갱신해야 할 때.

## 위치
`.harness/tasks/sprint-{N}/{phase_id}-handoff.md`
- 예: `.harness/tasks/sprint-1/phase-01-docs-update-handoff.md`

## 형식 (반드시 20줄 이내)

```markdown
# Handoff — {phase_id}

## 한 줄 요약
이 Phase가 무엇을 마쳤는지 한 문장.

## 변경된 파일 (경로만, 최대 10개)
- path/one
- path/two

## 다음 Phase가 알아야 할 사실
- 가정/제약 한 줄.
- 다음 Phase 입력에 영향을 주는 결정 한 줄.

## 검증 결과
- ruff: pass | <짧은 사유로 fail>
- mypy: pass | <짧은 사유로 fail>
- pytest: pass | skipped(이유) | fail(테스트명)
- structure: pass | fail

## 미해결 / 후속 작업 (있을 때만)
- 다음 Phase 또는 별도 PR로 미루는 항목 한 줄.
```

## 규칙
- **20줄 초과 금지.** 길어지면 컨텍스트 비용이 누적된다.
- 코드 블록 본문, 긴 stack trace, 전체 diff 금지. 위치(파일:라인)만 적는다.
- 다음 Phase 입력에 영향이 없는 내부 자잘한 변경은 적지 않는다.
- 검증 항목이 실행되지 않았으면 `skipped(이유)`로 명시.
- "TODO" 같은 빈 항목은 남기지 않는다. 작성하지 않을 거면 섹션째 생략한다.

## 절대 하지 말 것
- 전체 diff/로그 복붙.
- 다음 Phase가 다시 결정해야 할 내용을 "다음 Phase가 알아서 처리" 같은 모호한 문장으로 떠넘기기.
- 검증 명령을 실행하지 않고 임의로 "pass"라고 적기.
