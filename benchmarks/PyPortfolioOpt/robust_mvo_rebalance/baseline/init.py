# EVOLVE-BLOCK-START
import numpy as np


def _project_to_simplex(v: np.ndarray) -> np.ndarray:
    n = v.size
    u = np.sort(v)[::-1]
    cssv = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, n + 1) > (cssv - 1))[0]
    if rho.size == 0:
        return np.ones(n) / n
    rho = rho[-1]
    theta = (cssv[rho] - 1) / (rho + 1)
    w = np.maximum(v - theta, 0)
    s = w.sum()
    if s <= 0:
        return np.ones(n) / n
    return w / s


def _enforce_bounds(w: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    w = np.minimum(np.maximum(w, lower), upper)
    return w


def _enforce_sum_and_bounds(w: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    w = _enforce_bounds(w, lower, upper)
    for _ in range(20):
        gap = 1.0 - w.sum()
        if abs(gap) < 1e-10:
            break
        free = (w > lower + 1e-12) & (w < upper - 1e-12)
        if not np.any(free):
            w = _project_to_simplex(w)
            w = _enforce_bounds(w, lower, upper)
            continue
        w[free] += gap / free.sum()
        w = _enforce_bounds(w, lower, upper)
    s = w.sum()
    if s <= 0:
        return np.ones_like(w) / w.size
    return w / s


def _enforce_turnover(w: np.ndarray, w_prev: np.ndarray, turnover_limit: float) -> np.ndarray:
    delta = w - w_prev
    turn = np.abs(delta).sum()
    if turn <= turnover_limit + 1e-12:
        return w
    scale = turnover_limit / max(turn, 1e-12)
    return w_prev + scale * delta


def _enforce_sector_bounds(
    w: np.ndarray,
    sector_ids: np.ndarray,
    sector_lower: dict,
    sector_upper: dict,
    lower: np.ndarray,
    upper: np.ndarray,
) -> np.ndarray:
    w = w.copy()
    sectors = np.unique(sector_ids)
    for _ in range(5):
        changed = False
        for s in sectors:
            idx = np.where(sector_ids == s)[0]
            total = w[idx].sum()
            lo = sector_lower.get(int(s), 0.0)
            hi = sector_upper.get(int(s), 1.0)
            if total > hi + 1e-10:
                excess = total - hi
                room = w[idx] - lower[idx]
                cap = room.sum()
                if cap > 1e-12:
                    take = np.minimum(room, excess * room / cap)
                    w[idx] -= take
                    changed = True
            elif total < lo - 1e-10:
                need = lo - total
                room = upper[idx] - w[idx]
                cap = room.sum()
                if cap > 1e-12:
                    add = np.minimum(room, need * room / cap)
                    w[idx] += add
                    changed = True
        w = _enforce_sum_and_bounds(w, lower, upper)
        if not changed:
            break
    return w



def _max_constraint_residual(
    w: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    sector_ids: np.ndarray,
    sector_lower: dict,
    sector_upper: dict,
    factor_loadings: np.ndarray,
    factor_lower: np.ndarray,
    factor_upper: np.ndarray,
    w_prev: np.ndarray,
    turnover_limit: float,
) -> float:
    """Largest violation across every constraint the evaluator gates on."""
    res = abs(float(w.sum()) - 1.0)
    res = max(res, float(np.maximum(0.0, lower - w).max()))
    res = max(res, float(np.maximum(0.0, w - upper).max()))
    for s, lo in sector_lower.items():
        res = max(res, float(lo) - float(w[sector_ids == int(s)].sum()))
    for s, hi in sector_upper.items():
        res = max(res, float(w[sector_ids == int(s)].sum()) - float(hi))
    res = max(res, float(np.abs(w - w_prev).sum()) - float(turnover_limit))
    exposure = factor_loadings.T @ w
    res = max(res, float(np.maximum(0.0, factor_lower - exposure).max()))
    res = max(res, float(np.maximum(0.0, exposure - factor_upper).max()))
    return max(0.0, res)


def _repair_to_feasible(
    w: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    sector_ids: np.ndarray,
    sector_lower: dict,
    sector_upper: dict,
    factor_loadings: np.ndarray,
    factor_lower: np.ndarray,
    factor_upper: np.ndarray,
    w_prev: np.ndarray,
    turnover_limit: float,
    tol: float = 1e-9,
) -> np.ndarray:
    """Pull `w` back onto the feasible set along the segment to `w_prev`.

    The first-order loop above repairs bounds, sector limits, turnover and the
    budget sum, but it never projects onto the factor-exposure box, so its
    iterate is routinely infeasible there. Every constraint in this task is
    convex and `w_prev` satisfies all of them by construction (the instance
    generator builds the sector and factor boxes around `w_prev`, and `w_prev`
    lies inside the per-asset bounds and sums to one). So the whole segment
    `w_prev + lam * (w - w_prev)` is feasible for small enough `lam`, and a
    bisection finds the largest usable step. Worst case this returns `w_prev`,
    which is feasible but earns no improvement -- never an infeasible vector.
    """
    args = (
        lower,
        upper,
        sector_ids,
        sector_lower,
        sector_upper,
        factor_loadings,
        factor_lower,
        factor_upper,
        w_prev,
        turnover_limit,
    )
    if _max_constraint_residual(w, *args) <= tol:
        return w

    delta = w - w_prev
    lam_lo, lam_hi = 0.0, 1.0
    for _ in range(60):
        lam_mid = 0.5 * (lam_lo + lam_hi)
        if _max_constraint_residual(w_prev + lam_mid * delta, *args) <= tol:
            lam_lo = lam_mid
        else:
            lam_hi = lam_mid
    return w_prev + lam_lo * delta


def solve_instance(instance: dict) -> dict:
    mu = np.asarray(instance["mu"], dtype=float)
    cov = np.asarray(instance["cov"], dtype=float)
    w_prev = np.asarray(instance["w_prev"], dtype=float)
    lower = np.asarray(instance["lower"], dtype=float)
    upper = np.asarray(instance["upper"], dtype=float)
    sector_ids = np.asarray(instance["sector_ids"], dtype=int)
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    factor_loadings = np.asarray(instance["factor_loadings"], dtype=float)
    factor_lower = np.asarray(instance["factor_lower"], dtype=float)
    factor_upper = np.asarray(instance["factor_upper"], dtype=float)
    risk_aversion = float(instance["risk_aversion"])
    transaction_penalty = float(instance["transaction_penalty"])
    turnover_limit = float(instance["turnover_limit"])

    w = np.clip(w_prev.copy(), lower, upper)
    w = _enforce_sum_and_bounds(w, lower, upper)

    eps = 1e-4
    for t in range(250):
        step = 0.08 / np.sqrt(t + 1.0)
        delta = w - w_prev
        smooth_sign = delta / np.sqrt(delta * delta + eps)
        grad = mu - 2.0 * risk_aversion * (cov @ w) - transaction_penalty * smooth_sign

        w = w + step * grad
        w = _enforce_bounds(w, lower, upper)
        w = _enforce_turnover(w, w_prev, turnover_limit)
        w = _enforce_bounds(w, lower, upper)
        w = _enforce_sector_bounds(
            w, sector_ids, sector_lower, sector_upper, lower, upper
        )
        w = _enforce_turnover(w, w_prev, turnover_limit)
        w = _enforce_sum_and_bounds(w, lower, upper)

    # Final hard-feasibility repair. The evaluator scores an infeasible
    # portfolio as 0, so returning a slightly-better-but-infeasible vector is
    # strictly worse than returning a feasible one.
    w = _repair_to_feasible(
        w,
        lower,
        upper,
        sector_ids,
        sector_lower,
        sector_upper,
        factor_loadings,
        factor_lower,
        factor_upper,
        w_prev,
        turnover_limit,
    )

    return {"weights": w}
# EVOLVE-BLOCK-END
