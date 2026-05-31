---
name: adr-author
description: Author or update Architecture Decision Records under docs/adr/. Use when adding a new ADR, revising an existing one, or when the user makes an architecture-level decision that needs to be recorded. Triggers on phrases like "ADR 작성", "결정 사항 기록", "아키텍처 결정".
---

# ADR 작성·갱신 가이드

## 언제 트리거되는가
- 새로운 ADR을 작성하라는 요청.
- 기존 ADR을 부분적으로 수정·확장하라는 요청.
- 코드 변경이 ADR 갱신을 동반해야 하는 경우 (예: 새 검사 단계 추가, 새 파이프라인 도입, 의존성 방향 변경).

## 파일 위치 / 번호 규칙
- 위치: `docs/adr/NNNN-kebab-case-title.md`.
- 번호는 기존 ADR 중 최대값 + 1. 결번 만들지 말 것.
- 현재까지: 0001~0013 (`docs/adr/` 디렉터리 확인 후 다음 번호 결정).

## 본문 형식 (한국어)

```markdown
# ADR-NNNN: 짧은 제목

- **상태**: Proposed | Accepted | Superseded by ADR-XXXX
- **날짜**: YYYY-MM-DD
- **관련 ADR**: ADR-XXXX (있다면)

## 배경
무엇을 결정해야 했고 왜 결정이 필요했는지 2~5문장.

## 결정
이번 ADR이 내린 결정. 명확한 동사로 시작 ("X를 채택한다", "Y를 금지한다").

## 대안
검토했지만 채택하지 않은 선택지와 그 이유 (불릿 3개 이하).

## 결과
- 긍정적 결과
- 부정적 결과 / 트레이드오프
- 후속 조치 (필요 시): 코드 변경 위치, `harness_structure.yaml` 규칙 추가 등.

## 검증 방법
이 결정이 지켜지고 있는지 자동/수동 검증 방법.
(가능하면 `harness_structure.yaml`의 규칙으로 변환하거나 테스트 추가)
```

## 작성 체크리스트
- [ ] 번호가 디렉터리에서 다음 순번인지 확인.
- [ ] 결정 문장에 "한다/금지한다/채택한다" 같은 명확한 동사 사용.
- [ ] 영향 받는 코드 경로/디렉터리 명시.
- [ ] 새 의존성 방향 규칙이 생기면 `harness_structure.yaml`에 대응 규칙을 함께 추가.
- [ ] 기존 ADR을 대체한다면 그 ADR 상태를 `Superseded by ADR-NNNN`으로 갱신.
- [ ] 루트 `CLAUDE.md`의 ADR 목록 한 줄에 신규 항목 추가.

## 절대 하지 말 것
- 영어로 작성.
- "TBD"만 남긴 채 커밋.
- 본 ADR이 정한 규칙을 자동 검증으로 강제할 수 있는데 추가하지 않고 넘어가기.
