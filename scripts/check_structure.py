"""구조 분석 실행 스크립트. CI에서 독립 실행 가능."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.sensors.computational.structure_test import StructureAnalyzer


def main() -> None:
    analyzer = StructureAnalyzer(str(Path(__file__).parent.parent))
    result = analyzer.analyze()

    print(result.summary_for_llm)

    if result.violations:
        for v in result.violations:
            print(f"  {v.severity.upper()}: {v.file}:{v.line} [{v.rule_name}] {v.message}")

    # ADR 요약 출력
    adr_summary = analyzer.get_adr_summary()
    if adr_summary:
        print(f"\n{adr_summary}")

    if not result.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
