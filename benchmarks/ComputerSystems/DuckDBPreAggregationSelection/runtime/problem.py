from __future__ import annotations

from .duckdb_local_workload import PREAGGREGATION_WORKLOAD_MANIFEST, measure_preaggregation_design, normalize_name_list


WORKLOAD_MANIFEST = dict(PREAGGREGATION_WORKLOAD_MANIFEST)


def load_instance():
    return dict(WORKLOAD_MANIFEST)


def evaluate_selection(selection):
    return measure_preaggregation_design(normalize_name_list(selection, "preaggregations"))
