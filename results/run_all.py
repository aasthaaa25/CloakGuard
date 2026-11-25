"""Run the local CloakGuard research checks from any working directory."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for command in (
        ["evaluation/demo_case.py"],
        ["evaluation/run_live_demo.py"],
        ["evaluation/benchmark_url_proxy.py"],
        ["evaluation/benchmark_controlled_ml.py"],
        ["evaluation/stress_controlled_ml.py"],
        ["evaluation/benchmark_repeat_review.py"],
        ["testbed/defense_checks.py"],
        ["-m", "pytest", "results/tests", "-q"],
    ):
        result = subprocess.run([sys.executable, *command], cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
