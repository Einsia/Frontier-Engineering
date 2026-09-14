# IMPORTANT (OpenEvolve contract):
# - The evaluator runs this script as:
#     python <program.py> --output prediction.h5ad --dataset-dir <CACHE_DIR>
# - Do NOT change these CLI flags or introduce additional REQUIRED args.
# - You MUST write a valid AnnData to --output with:
#     - layers["normalized"] shape (n_test_cells, n_mod2_features)
#     - obs matching test_mod1.obs (same cells/order)
#     - var matching train_mod2.var (same features/order)
#     - uns["dataset_id"] present and uns["method_id"] set

# EVOLVE-BLOCK-START
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import anndata as ad
import numpy as np
from scipy.sparse import csc_matrix


DATASET_ID = "openproblems_neurips2021/bmmc_cite/normal/log_cp10k"
BASE_URL = (
    "https://openproblems-data.s3.amazonaws.com/"
    "resources/task_predict_modality/datasets/openproblems_neurips2021/bmmc_cite/normal/log_cp10k/"
)


def _repo_root(start: Path) -> Path:
    here = start.resolve()
    for parent in [here, *here.parents]:
        if (parent / "benchmarks").is_dir():
            return parent
    return here


def _download(url: str, dest: Path, *, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for _ in range(max(1, retries)):
        tmp = dest.parent / f".{dest.name}.tmp.{os.getpid()}.{time.time_ns()}"
        try:
            with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f)
            tmp.replace(dest)
            return
        except Exception as e:  # pragma: no cover
            last_err = e
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(1.0)
    raise RuntimeError(f"Failed to download {url} -> {dest}: {last_err}")


def _ensure_inputs(dataset_dir: Path) -> tuple[Path, Path, Path]:
    test_mod1 = dataset_dir / "test_mod1.h5ad"
    train_mod1 = dataset_dir / "train_mod1.h5ad"
    train_mod2 = dataset_dir / "train_mod2.h5ad"
    for name, path in (
        ("test_mod1.h5ad", test_mod1),
        ("train_mod1.h5ad", train_mod1),
        ("train_mod2.h5ad", train_mod2),
    ):
        if not path.is_file():
            _download(BASE_URL + name, path)
    return test_mod1, train_mod1, train_mod2


def _to_h5ad_compatible_frame(df):
    """Convert string-like metadata to plain Python objects for h5ad."""
    out = df.copy()
    out.index = out.index.astype(str).astype(object)
    for column in out.columns:
        dtype_name = str(getattr(out[column].dtype, "name", out[column].dtype))
        if ("string" in dtype_name) or (dtype_name == "category") or (dtype_name == "object"):
            out[column] = out[column].astype(str).astype(object)
    return out


def run_mean_per_gene(*, dataset_dir: Path, output: Path) -> None:
    test_mod1_path, train_mod1_path, train_mod2_path = _ensure_inputs(dataset_dir)
    test1 = ad.read_h5ad(str(test_mod1_path))
    train1 = ad.read_h5ad(str(train_mod1_path))
    train2 = ad.read_h5ad(str(train_mod2_path))
    xtr = train1.layers.get("normalized", train1.X)
    xte = test1.layers.get("normalized", test1.X)
    ytr = train2.layers.get("normalized")
    if ytr is None:
        raise ValueError("train_mod2.h5ad missing layers['normalized']")
    xtr = np.asarray(xtr.toarray() if hasattr(xtr, "toarray") else xtr, dtype=np.float32)
    xte = np.asarray(xte.toarray() if hasattr(xte, "toarray") else xte, dtype=np.float32)
    ytr = np.asarray(ytr.toarray() if hasattr(ytr, "toarray") else ytr, dtype=np.float32)

    mu = xtr.mean(0, dtype=np.float32)
    xtr = xtr - mu
    xte = xte - mu

    k = min(64, max(8, min(xtr.shape) - 1))
    try:
        _, _, vt = np.linalg.svd(xtr, full_matrices=False)
        basis = vt[:k].T.astype(np.float32, copy=False)
        ztr = xtr @ basis
        zte = xte @ basis
    except np.linalg.LinAlgError:
        ztr = xtr
        zte = xte

    lam = np.float32(1.0)
    a = ztr.T @ ztr
    a.flat[:: a.shape[0] + 1] += lam
    b = ztr.T @ ytr
    coef = np.linalg.solve(a, b).astype(np.float32, copy=False)
    intercept = (ytr.mean(0) - ztr.mean(0) @ coef).astype(np.float32, copy=False)
    pred = np.maximum(zte @ coef + intercept, 0.0).astype(np.float32, copy=False)

    out = ad.AnnData(
        layers={"normalized": csc_matrix(pred)},
        shape=pred.shape,
        obs=_to_h5ad_compatible_frame(test1.obs),
        var=_to_h5ad_compatible_frame(train2.var),
        uns={"dataset_id": test1.uns.get("dataset_id", DATASET_ID), "method_id": "pca_ridge_modality"},
    )
    out.write_h5ad(str(output), compression="gzip")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("prediction.h5ad"))
    p.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Cache directory for downloaded OpenProblems files (default: <benchmark>/resources_cache).",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root(Path(__file__).resolve())
    if args.dataset_dir is None:
        args.dataset_dir = (
            repo_root
            / "benchmarks"
            / "SingleCellAnalysis"
            / "predict_modality"
            / "resources_cache"
            / "openproblems_neurips2021__bmmc_cite__normal__log_cp10k"
        )
    run_mean_per_gene(dataset_dir=args.dataset_dir, output=args.output)
    print(json.dumps({"output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
# EVOLVE-BLOCK-END
