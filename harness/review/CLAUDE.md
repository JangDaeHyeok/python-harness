# harness/review — 리뷰 산출물·PR 자동화 로컬 규칙

## 책임
- `artifacts.py` / `intent.py` / `criteria.py` — 설계 의도, 평가 기준 산출물.
- `conventions.py` — 코드 컨벤션 로더.
- `pr_body.py` — PR 본문 생성.
- `reflection.py` — 리뷰 코멘트 분류·반영 로그.
- `worktree.py` / `session_fork.py` — 격리 실행.
- `docs_diff.py` — Phase 간 문서 변경 추적.
- `pipeline_integration.py` — 파이프라인 진입점.

## 로컬 규칙
- **`harness/review/`는 `harness/agents/`를 import 하지 않는다** (단방향). 구조 검사로 강제됨.
- 리뷰 산출물 경로는 `.harness/review-artifacts/{branch}/` 하위에 둔다. 경로 조립은 `artifacts.py`의 헬퍼를 사용한다.
- 셸 명령(`git`, `gh`)은 `harness/tools/shell.py`를 통해 호출한다.
- 모든 산출물 본문은 한국어로 작성한다 (PR 본문, 답글, 판단 로그 포함).

## PR 자동화 정책 (요약, 상세는 docs/operations.md §4)
- 리뷰 코멘트 판정: `ACCEPT` / `DEFER` / `IGNORE`. **ACCEPT 만** `claude --print` 리뷰 반영 세션에 전달.
- 반영 커밋이 push된 경우에만 원본 코멘트에 한국어 답글을 남긴다.
- review thread resolve는 답글 기반 확인으로 대체 (GitHub API 제약).
- CodeRabbit은 외부 리뷰어로 동일 분류 흐름을 탄다. optional/nit/칭찬성은 DEFER.
- 분류 보조 신호(`scripts/auto_pr_pipeline.py`의 `classify_review_comment`): 액션 키워드는 단어 경계 매칭(`debug`가 `bug`로 오탐되지 않음), CodeRabbit `⚠️ Potential issue`/`_critical_`는 ACCEPT·`🧹 Nitpick`/`🛠️ Refactor`는 DEFER 가중, `author_association`(MEMBER/OWNER/COLLABORATOR)은 신뢰 가중이되 단독 ACCEPT 금지. 리뷰 본문은 계속 신뢰 불가 입력으로 취급(신호 추출에만 사용).

## 관련 ADR
- 0004 리뷰 산출물 워크플로, 0009 Phase 실행과 컨텍스트 격리.
