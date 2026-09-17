from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from generator import SCENARIO_SPECS, generate_scenario
from problem_view import candidate_view


TASK_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = TASK_ROOT / "references" / "baseline_init_v1.py"
OUTPUT_PATH = TASK_ROOT / "references" / "anchor_solutions_v1.json"


def main() -> None:
    anchors: dict[str, list[int]] = {}

    for scenario_name in SCENARIO_SPECS:
        problem = generate_scenario(scenario_name)

        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            problem_path = directory_path / "problem.json"
            solution_path = directory_path / "solution.json"

            problem_path.write_text(
                json.dumps(candidate_view(problem), indent=2),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CANDIDATE_PATH),
                    "--problem",
                    str(problem_path),
                    "--output",
                    str(solution_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"{scenario_name} 运行失败：{result.stderr}"
                )

            solution = json.loads(
                solution_path.read_text(encoding="utf-8")
            )

            anchors[scenario_name] = solution["selected_ids"]

    OUTPUT_PATH.write_text(
        json.dumps(anchors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"已保存 {len(anchors)} 个参照答案")
    print(f"位置：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
