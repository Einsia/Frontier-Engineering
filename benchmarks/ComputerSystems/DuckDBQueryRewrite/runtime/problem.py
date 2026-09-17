from __future__ import annotations

from .duckdb_local_workload import ORIGINAL_QUERY_SQL, QUERY_REWRITE_MANIFEST, measure_query_rewrite


WORKLOAD_MANIFEST = dict(QUERY_REWRITE_MANIFEST)


def load_instance():
    return {"sql": ORIGINAL_QUERY_SQL, "manifest": dict(WORKLOAD_MANIFEST)}


def evaluate_query(value):
    if isinstance(value, dict):
        if "sql" not in value:
            raise ValueError("missing sql")
        value = value["sql"]
    return measure_query_rewrite(str(value))
