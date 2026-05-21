---
status: accepted
date: 2026-05-20
---

# ADR-0011: harness-init 마이그레이션 모드 도입

## Context

Python Harness를 기존 외부 Python 프로젝트에 적용할 때 프로젝트별 레이아웃을
유연하게 지원하면 Planner, Generator, Evaluator가 참조하는 구조 규칙과 운영
가이드가 흔들린다. 하네스는 외부 프로젝트가 정해진 구조에 맞추는 방식을 선택한다.

## Decision

- `harness-init --migrate`를 기존 Python 프로젝트 보강 경로로 제공한다.
- 마이그레이션은 누락된 하네스 필수 파일과 디렉터리만 생성하고, 기존 프로젝트의
  README, CLAUDE.md, `.claude/skills/`는 건드리지 않는다.
- 패키지명은 `pyproject.toml`, top-level 패키지, `src/*` 패키지 후보에서 추론하되,
  후보가 여러 개면 `.harness/project-policy.yaml`의 `project.package`를 명시하게 한다.
- 외부 프로젝트용 `harness_structure.yaml`은 정책의 package 값을 사용해 검사 범위를
  고정한다.

## Consequences

- 기존 프로젝트를 하네스 구조로 옮길 때 사용자 파일 침범을 줄일 수 있다.
- 다중 레이아웃 호환성 대신 명확한 실패 메시지와 정책 기반 패키지 선택을 제공한다.
- 마이그레이션 후 사용자는 생성된 ADR과 정책 파일을 검토한 뒤 `harness` 실행으로
  첫 스프린트를 시작해야 한다.
