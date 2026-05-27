"""센서 실행 도구 미설치 회귀 테스트."""

from __future__ import annotations

import subprocess
import sys
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


def test_test_runner_missing_pytest_module_fails_as_env_error(
    tmp_path: Path,
) -> None:
    sensor = PytestRunnerSensor(str(tmp_path))
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr=f"{sys.executable}: No module named pytest",
    )

    with patch("subprocess.run", return_value=completed):
        result = sensor.run_pytest()

    assert not result.passed
    assert result.summary_for_llm == (
        "[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요."
    )


def test_test_runner_simple_missing_pytest_module_fails_as_env_error(
    tmp_path: Path,
) -> None:
    sensor = PytestRunnerSensor(str(tmp_path))
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr=f"{sys.executable}: No module named pytest",
    )

    with patch("subprocess.run", return_value=completed):
        result = sensor.run_pytest_simple()

    assert not result.passed
    assert result.summary_for_llm == (
        "[ENV] pytest이(가) 설치되어 있지 않습니다. pip install pytest 후 다시 시도하세요."
    )


def test_test_runner_uses_current_python_for_pytest(tmp_path: Path) -> None:
    sensor = PytestRunnerSensor(str(tmp_path))
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=5,
        stdout="",
        stderr="no tests collected",
    )

    with patch("subprocess.run", return_value=completed) as run:
        sensor.run_pytest()

    assert run.call_args.args[0][0] == sys.executable


def test_test_runner_simple_uses_current_python_for_pytest(tmp_path: Path) -> None:
    sensor = PytestRunnerSensor(str(tmp_path))
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=5,
        stdout="",
        stderr="no tests collected",
    )

    with patch("subprocess.run", return_value=completed) as run:
        sensor.run_pytest_simple()

    assert run.call_args.args[0][0] == sys.executable


def test_test_runner_fails_when_coverage_below_policy(tmp_path: Path) -> None:
    sensor = PytestRunnerSensor(str(tmp_path), min_coverage=90)
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="TOTAL      10      2    80%\n",
        stderr="",
    )

    with patch("subprocess.run", return_value=completed):
        result = sensor.run_pytest_simple()

    assert not result.passed
    assert result.coverage_percent == 80
    assert "커버리지 기준 미달" in result.summary_for_llm


def test_test_runner_uses_configured_command_and_timeout(tmp_path: Path) -> None:
    sensor = PytestRunnerSensor(str(tmp_path), command="pytest -q", timeout=12)
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    with patch("subprocess.run", return_value=completed) as run:
        sensor.run_pytest_simple()

    assert run.call_args.args[0][:4] == [sys.executable, "-m", "pytest", "-q"]
    assert run.call_args.kwargs["timeout"] == 12
