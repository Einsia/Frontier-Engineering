from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluator import (
    END_MARKER,
    START_MARKER,
    evaluate,
    run_candidate,
)
from generator import SCENARIO_SPECS, generate_scenario
from scoring import score_selection


TASK_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = TASK_ROOT / "scripts" / "init.py"
CLEAN_PATH = (
    TASK_ROOT
    / "references"
    / "clean_candidate_v1.py"
)
ANCHOR_PATH = (
    TASK_ROOT
    / "references"
    / "anchor_solutions_v1.json"
)


def require(condition: bool, message: str) -> None:
    """条件不满足时，立即报告具体测试失败。"""
    if not condition:
        raise AssertionError(message)


def contains_error(
    result: dict[str, Any],
    keyword: str,
) -> bool:
    return any(
        keyword in str(error)
        for error in result["errors"]
    )


def replace_with_wrong_domain(
    problem: dict[str, Any],
    anchor_ids: list[int],
) -> list[int]:
    items_by_id = {
        item["id"]: item
        for item in problem["items"]
    }

    selected_set = set(anchor_ids)

    old_id = next(
        item_id
        for item_id in anchor_ids
        if items_by_id[item_id]["domain"] == "memory"
    )

    new_id = next(
        item["id"]
        for item in problem["items"]
        if (
            item["domain"] == "reasoning"
            and item["id"] not in selected_set
        )
    )

    trial = anchor_ids.copy()
    trial[trial.index(old_id)] = new_id
    return trial


def create_enemy_conflict(
    problem: dict[str, Any],
    anchor_ids: list[int],
) -> list[int]:
    items_by_id = {
        item["id"]: item
        for item in problem["items"]
    }

    groups: dict[str, list[int]] = defaultdict(list)

    for item in problem["items"]:
        group = item["enemy_group"]

        if group is not None:
            groups[group].append(item["id"])

    for pair_ids in groups.values():
        if len(pair_ids) < 2:
            continue

        pair = pair_ids[:2]
        domain = items_by_id[pair[0]]["domain"]

        trial = anchor_ids.copy()
        missing = [
            item_id
            for item_id in pair
            if item_id not in trial
        ]

        removable = [
            item_id
            for item_id in trial
            if (
                items_by_id[item_id]["domain"] == domain
                and item_id not in pair
            )
        ]

        if len(removable) < len(missing):
            continue

        for old_id, new_id in zip(
            removable,
            missing,
        ):
            trial[trial.index(old_id)] = new_id

        result = score_selection(problem, trial)

        if contains_error(result, "材料冲突"):
            return trial

    raise AssertionError(
        "测试程序未能构造材料冲突答案"
    )


def select_extreme_items(
    problem: dict[str, Any],
    field: str,
) -> list[int]:
    selected_ids: list[int] = []

    for domain, target in (
        problem["domain_targets"].items()
    ):
        candidates = [
            item
            for item in problem["items"]
            if item["domain"] == domain
        ]

        candidates.sort(
            key=lambda item: (
                -float(item[field]),
                item["id"],
            )
        )

        selected_ids.extend(
            item["id"]
            for item in candidates[:target]
        )

    return selected_ids


def main() -> None:
    anchors = json.loads(
        ANCHOR_PATH.read_text(encoding="utf-8")
    )

    # 1. 同一场景必须每次生成完全相同的题库。
    generated_once = generate_scenario(
        "dev_balanced"
    )
    generated_twice = generate_scenario(
        "dev_balanced"
    )

    require(
        generated_once == generated_twice,
        "题库生成不具有确定性",
    )

    # 2. 十个固定参照答案都必须合法。
    valid_anchor_count = 0

    for scenario_name in SCENARIO_SPECS:
        problem = generate_scenario(scenario_name)
        result = score_selection(
            problem,
            anchors[scenario_name],
        )

        require(
            result["valid"],
            (
                f"参照答案在 {scenario_name} "
                f"中不合法：{result['errors']}"
            ),
        )
        valid_anchor_count += 1

    # 3. 普通算法对相同场景必须给出相同答案。
    baseline_problem = generate_scenario(
        "dev_balanced"
    )

    first_ids, first_error = run_candidate(
        BASELINE_PATH,
        baseline_problem,
    )
    second_ids, second_error = run_candidate(
        BASELINE_PATH,
        baseline_problem,
    )

    require(
        not first_error and not second_error,
        "普通算法运行失败",
    )
    require(
        first_ids == second_ids,
        "普通算法不具有确定性",
    )

    baseline_source = BASELINE_PATH.read_text(
        encoding="utf-8"
    )

    with tempfile.TemporaryDirectory(
        dir=TASK_ROOT
    ) as directory:
        directory_path = Path(directory)

        inside_candidate = directory_path / "inside.py"
        inside_candidate.write_text(
            baseline_source.replace(
                "def item_information(",
                "# allowed change\ndef item_information(",
                1,
            ),
            encoding="utf-8",
        )
        inside_metrics, _ = evaluate(inside_candidate)

        require(
            inside_metrics["valid"] == 1.0,
            "change inside EVOLVE-BLOCK was rejected",
        )

        outside_candidate = directory_path / "outside.py"
        outside_candidate.write_text(
            baseline_source.replace(
                "parser = argparse.ArgumentParser()",
                "parser = argparse.ArgumentParser(description='changed')",
                1,
            ),
            encoding="utf-8",
        )
        outside_metrics, _ = evaluate(outside_candidate)

        require(
            outside_metrics["valid"] == 0.0
            and outside_metrics["combined_score"] == 0.0,
            "change outside EVOLVE-BLOCK was accepted",
        )

        nondeterministic_candidate = (
            directory_path / "nondeterministic.py"
        )
        nondeterministic_candidate.write_text(
            baseline_source.replace(
                '    return [item["id"] for item in selected]',
                """    state_path = Path(__file__).with_suffix(".state")
    if state_path.exists():
        state_path.unlink()
        selected.reverse()
    else:
        state_path.touch()

    return [item["id"] for item in selected]""",
                1,
            ),
            encoding="utf-8",
        )
        nondeterministic_metrics, _ = evaluate(
            nondeterministic_candidate
        )

        require(
            nondeterministic_metrics["valid"] == 0.0
            and nondeterministic_metrics["combined_score"] == 0.0,
            "nondeterministic candidate was accepted",
        )

        clean_candidate = directory_path / "clean.py"
        clean_block = CLEAN_PATH.read_text(
            encoding="utf-8"
        ).split("\ndef main() -> None:", 1)[0]
        baseline_after = baseline_source.partition(
            END_MARKER
        )[2]
        clean_candidate.write_text(
            START_MARKER
            + "\n"
            + clean_block
            + "\n\ndef select_items(problem: dict[str, Any]) -> list[int]:\n"
            + "    return improve_selection(problem)\n\n"
            + END_MARKER
            + baseline_after,
            encoding="utf-8",
        )
        clean_metrics, _ = evaluate(clean_candidate)

    # 4. 正式运行普通算法，应为有效的50分。
    baseline_metrics, _ = evaluate(
        BASELINE_PATH
    )

    require(
        baseline_metrics["valid"] == 1.0,
        "普通算法被正式裁判判为无效",
    )
    require(
        abs(
            baseline_metrics["combined_score"]
            - 50.0
        )
        < 1e-9,
        "普通算法没有保持50分参照线",
    )

    # 5. 独立改进算法必须明显优于普通算法。
    require(
        clean_metrics["valid"] == 1.0,
        "独立改进算法存在无效场景",
    )
    require(
        clean_metrics["combined_score"] >= 65.0,
        (
            "独立算法提升不足："
            f"{clean_metrics['combined_score']}"
        ),
    )

    # 6. 精确检查几类错误答案。
    problem = generate_scenario(
        "dev_balanced"
    )
    anchor_ids = anchors["dev_balanced"]

    duplicate_result = score_selection(
        problem,
        [1] * problem["test_length"],
    )
    require(
        not duplicate_result["valid"]
        and contains_error(
            duplicate_result,
            "重复题号",
        ),
        "裁判没有识别重复题号",
    )

    unknown_ids = anchor_ids.copy()
    unknown_ids[-1] = 999

    unknown_result = score_selection(
        problem,
        unknown_ids,
    )
    require(
        not unknown_result["valid"]
        and contains_error(
            unknown_result,
            "未知题号",
        ),
        "裁判没有识别不存在的题号",
    )

    wrong_domain_ids = replace_with_wrong_domain(
        problem,
        anchor_ids,
    )
    wrong_domain_result = score_selection(
        problem,
        wrong_domain_ids,
    )
    require(
        not wrong_domain_result["valid"]
        and contains_error(
            wrong_domain_result,
            "数量错误",
        ),
        "裁判没有识别领域数量错误",
    )

    conflict_ids = create_enemy_conflict(
        problem,
        anchor_ids,
    )
    conflict_result = score_selection(
        problem,
        conflict_ids,
    )
    require(
        not conflict_result["valid"]
        and contains_error(
            conflict_result,
            "材料冲突",
        ),
        "裁判没有识别相似材料冲突",
    )

    fast_problem = generate_scenario(
        "dev_fast_screening"
    )
    slow_ids = select_extreme_items(
        fast_problem,
        "time",
    )
    slow_result = score_selection(
        fast_problem,
        slow_ids,
    )
    require(
        not slow_result["valid"]
        and contains_error(
            slow_result,
            "总时间超限",
        ),
        "裁判没有识别总时间超限",
    )

    fairness_problem = generate_scenario(
        "dev_fairness_sensitive"
    )
    high_dif_ids = select_extreme_items(
        fairness_problem,
        "dif_risk",
    )
    high_dif_result = score_selection(
        fairness_problem,
        high_dif_ids,
    )
    require(
        not high_dif_result["valid"]
        and contains_error(
            high_dif_result,
            "DIF",
        ),
        "裁判没有识别 DIF 风险超限",
    )

    security_problem = generate_scenario(
        "dev_security_sensitive"
    )
    high_exposure_ids = select_extreme_items(
        security_problem,
        "exposure",
    )
    high_exposure_result = score_selection(
        security_problem,
        high_exposure_ids,
    )
    require(
        not high_exposure_result["valid"]
        and contains_error(
            high_exposure_result,
            "曝光率",
        ),
        "裁判没有识别曝光率超限",
    )

    # 7. 进行一次端到端错误程序测试。
    with tempfile.TemporaryDirectory() as directory:
        bad_candidate = (
            Path(directory)
            / "bad_candidate.py"
        )

        bad_candidate.write_text(
            baseline_source.replace(
                '    return [item["id"] for item in selected]',
                '    return [1] * problem["test_length"]',
                1,
            ),
            encoding="utf-8",
        )

        bad_metrics, _ = evaluate(
            bad_candidate
        )

    require(
        bad_metrics["valid"] == 0.0,
        "端到端裁判错误地接受了非法程序",
    )
    require(
        bad_metrics["combined_score"] == 0.0,
        "非法程序的正式得分没有归零",
    )

    summary = {
        "all_tests_passed": True,
        "deterministic_generator": True,
        "deterministic_baseline": True,
        "valid_anchor_scenarios": (
            valid_anchor_count
        ),
        "baseline_score": (
            baseline_metrics["combined_score"]
        ),
        "clean_candidate_score": (
            clean_metrics["combined_score"]
        ),
        "rejected_error_types": [
            "duplicate_item_ids",
            "unknown_item_id",
            "wrong_domain_counts",
            "enemy_group_conflict",
            "time_limit",
            "dif_limit",
            "exposure_limit",
            "end_to_end_invalid_candidate",
            "outside_evolve_block",
            "nondeterministic_candidate",
        ],
    }

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()



task="$HOME/projects/Frontier-Engineering/benchmarks/AssessmentEngineering/RobustTestAssembly"
