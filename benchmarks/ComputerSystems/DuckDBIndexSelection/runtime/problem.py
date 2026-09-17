from __future__ import annotations

from .duckdb_local_workload import INDEX_WORKLOAD_MANIFEST, measure_index_design, normalize_name_list


WORKLOAD_MANIFEST = dict(INDEX_WORKLOAD_MANIFEST)


def load_instance():
    return dict(WORKLOAD_MANIFEST)


def evaluate_selection(selection):
    return measure_index_design(normalize_name_list(selection, "indexes"))
