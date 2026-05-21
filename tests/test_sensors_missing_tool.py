"""센서 실행 도구 미설치 회귀 테스트."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from harness.sensors.computational.linter import LinterSensor
from harness.sensors.computational.test_runner import TestRunnerSensor as PytestRunnerSensor
from harness.sensors.computational.type_checker import TypeCheckerSensor

if TYPE_CHECKING:
    from pathlib import Path


def test_linter_missing_ruff_fails(tmp_path: Path) -> None:
    sensor = LinterSensor(str(tmp_path))

    with patch("subprocess.run", side_effect=FileNotFoundError("ruff not found")):
        result = sensor.run_ruff()

    assert not result.passed
    assert result.total_errors == 1
    assert result.summary_for_llm == (
        "[ENV] ruff이(가) 설치되어 있지 않습니다. pip install ruff 후 다시 시도하세요."
    )


def test_linter_run_all_preserves_missing_ruff_message(tmp_path: Path) -> None:
    sensor = LinterSensor(str(tmp_path), custom_rules=[])

    with patch("subprocess.run", side_effect=FileNotFoundError("ruff not found")):
        result = sensor.run_all()

    assert not result.passed
    assert result.summary_for_llm == (
        "[ENV] ruff이(가) 설치되어 있지 않습니다. pip install ruff 후 다시 시도하세요."
    )


def test_type_checker_missing_mypy_fails(tmp_path: Path) -> None:
    sensor = TypeCheckerSensor(str(tmp_path))

    with patch("subprocess.run", side_effect=FileNotFoundError("mypy not found")):
        result = sensor.run_mypy()

    assert not result.passed
    assert result.total_errors == 1
    assert result.summary_for_llm == (
        "[ENV] mypy이(가) 설치되어 있지 않습니다. pip install mypy 후 다시 시도하세요."
    )


def test_test_runner_missing_pytest_fails(tmp_path: Path) -> None:
    sensor = PytestRunnerSensor(str(tmp_path))

    with patch("subprocess.run", side_effect=FileNotFoundError("pytest not found")):
        result = sensor.run_pytest()

    assert not result.passed
    assert result.summary_for_llm == (
        "[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요."
    )


def test_test_runner_simple_missing_pytest_fails(tmp_path: Path) -> None:
    sensor = PytestRunnerSensor(str(tmp_path))

    with patch("subprocess.run", side_effect=FileNotFoundError("pytest not found")):
        result = sensor.run_pytest_simple()

    assert not result.passed
    assert result.summary_for_llm == (
        "[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요."
    )
