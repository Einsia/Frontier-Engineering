from __future__ import annotations

from copy import deepcopy
from typing import Any


PRIVATE_FIELDS = {
    "problem_version",
    "scenario",
    "seed",
    "feedback",
}


def candidate_view(
    problem: dict[str, Any],
) -> dict[str, Any]:
    """
    生成交给候选程序的公开题目。

    裁判仍保留场景名称、随机种子和反馈类型，
    但候选程序只能看到完成组卷真正需要的信息。
    """
    public_problem = {
        key: value
        for key, value in problem.items()
        if key not in PRIVATE_FIELDS
    }

    return deepcopy(public_problem)
