# ADR-0015: 지식 DB 누적과 메타데이터 기반 유사 RAG

- **상태**: Accepted
- **날짜**: 2026-06-13
- **관련 ADR**: ADR-0004, ADR-0007, ADR-0008, ADR-0012
- **태그**: knowledge, rag, adr, context, pr
- **영향 경로**: harness/tools/adr.py, harness/guides/context_filter.py, harness/context/knowledge.py, harness/context/modify_context.py, harness/review/pr_body.py, harness/review/criteria.py

## 배경

ADR-0007은 가이드 레지스트리와 유사 RAG 컨텍스트 필터를 도입했지만, 초기 구현에는 다음 한계가 있었다.

- `ADRLoader`의 상태 파싱이 `status:` 영어 frontmatter만 인식해, 한국어 헤더(`- **상태**: Accepted`)로 작성된 ADR(0010·0012·0013·0014)이 모두 `unknown`으로 분류됐다. 그 결과 이 ADR들은 평가 기준 생성(`CriteriaGenerator`)과 관련도 가중에서 통째로 누락됐다.
- `ContextFilter`는 단순 키워드 카운트만 사용했고, ADR의 태그·범위·영향 경로·번호 같은 메타데이터나 변경 파일 경로를 활용하지 못했다. 한국어 2글자 핵심어(센서, 정책, 계약 등)도 길이 기준으로 과도하게 누락됐다.
- modify 계획 수립 시 Planner에게 ADR 제목·상태만 전달했고, 핵심 본문(결정·이유)은 제공하지 않았다.
- PR 본문은 변경 내용과 무관하게 항상 고정된 ADR-0010 문구를 넣었다.
- 실행 이력·판정·실패 원인·적용 ADR이 어디에도 누적되지 않아, 이후 작업이 과거 결정을 참조할 수 없었다.

## 결정

로컬 파일 기반(외부 벡터 DB·서버 없음) 결정적 검색만으로 ADR/정책/이력을 "나중에 참조 가능한 지식"으로 활용한다.

1. **ADR 메타데이터 추출 확장** (`harness/tools/adr.py`)
   - 상태 파싱을 frontmatter와 한국어 헤더(`- **상태**: ...`) 양쪽으로 확장하고 대소문자를 무시해 소문자로 정규화한다.
   - frontmatter와 한국어 헤더 불릿에서 `tags`/`scope`/`affected_paths`/`related_adrs`/`date`와 ADR 번호를 추출한다. 값이 없으면 빈 문자열로 폴백하므로 기존 ADR과 호환된다.
   - 핵심 섹션(배경/결정/이유/결과) 추출을 공용 함수 `extract_key_sections`로 제공한다.

2. **메타데이터 기반 유사 RAG** (`harness/guides/context_filter.py`)
   - 키워드 추출에서 한글 2글자를 허용하고(영문은 3글자 이상), `adr-0010` 같은 번호 토큰을 인식한다.
   - 제목·태그·범위·번호·영향 경로 매칭에 가중치를 부여하고, 변경 파일 경로(`affected_files`)와 ADR 영향 경로의 겹침을 점수에 반영한다.
   - 각 ADR이 선택된 이유(`selection_reasons`)를 기록해 산출물에 노출한다.

3. **지식 누적 스토어** (`harness/context/knowledge.py`)
   - `.harness/knowledge/entries.jsonl`(append, 상한 500)과 `index.json`(ADR 적용 횟수·상위 실패 원인)으로 실행 이력·적용 ADR·판정·실패 원인·점수를 누적한다.
   - 결정적 키워드 검색(`relevant`)과 최근순 조회(`recent`)를 제공하며, 기록 실패는 예외를 전파하지 않는다.

4. **참조 경로 연결**
   - modify 컨텍스트는 요청과 관련된 ADR 핵심 본문을 Planner에 주입하고, 관련 과거 이력을 함께 제공한다.
   - `CriteriaGenerator`/`ContextFilter`/`PRBodyGenerator`는 `ProjectPolicy.external_adr_sources`를 일관되게 반영한다.
   - PR 본문은 변경 파일·요약과 관련 있는 accepted ADR을 동적으로 선별해 근거를 적고, 관련 과거 이력을 덧붙인다.
   - 리뷰 반영 로그(review-comments)는 적용 ADR과 결정적 파이프라인 검증 결과를 판정 근거로 남긴다.

## 대안

- 외부 벡터 DB/임베딩 검색 도입: 운영 복잡도와 비결정성을 키우므로 채택하지 않는다(ADR-0002의 결정적 우선 원칙과도 상충).
- ADR 포맷을 frontmatter로 일괄 마이그레이션: 기존 한국어 헤더 ADR을 전부 고쳐야 하므로, 두 형식을 모두 읽는 하위 호환 파서를 택한다.

## 결과

- 긍정: 한국어 헤더 ADR이 정상 분류되어 평가 기준·관련도에 반영된다. 변경 범위에 맞는 ADR 근거가 컨텍스트·PR에 자동 포함된다.
- 긍정: 실행 이력이 누적되어 Planner/PR이 과거 실패 패턴과 적용 ADR을 참조할 수 있다.
- 트레이드오프: ADR 메타데이터(`태그`/`영향 경로` 등)는 선택 사항이라 작성되지 않으면 경로 매칭 신호가 약해진다. 작성을 권장하되 강제하지 않는다.

## 검증 방법

- `tests/test_review_criteria.py`에서 한국어 상태·frontmatter 메타데이터 추출과 external 소스 반영을 검증한다.
- `tests/test_context_filter.py`에서 2글자 키워드·번호·영향 경로 매칭과 선택 이유 기록을 검증한다.
- `tests/test_knowledge.py`에서 누적·인덱스·관련도 검색·손상 줄 무시를 검증한다.
- `tests/test_modify_context.py`/`tests/test_review_pr_body.py`에서 ADR 본문 주입과 동적 PR 근거를 검증한다.
- `ruff check .`, `mypy harness`, `python3 scripts/check_structure.py`, `pytest`가 모두 통과해야 한다.
