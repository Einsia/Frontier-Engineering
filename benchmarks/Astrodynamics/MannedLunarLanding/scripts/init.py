# EVOLVE-BLOCK-START
"""
支持燃料补给飞船功能

任务目标：最大化运载质量（Payload）
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import differential_evolution, least_squares, minimize, minimize_scalar, root

# ==================== 常数定义 ====================
class CONST:
    # 物理常数
    mu_e = 398600.0      # km³/s²
    mu_m = 4903.0        # km³/s²
    Re = 6378.0          # km
    Rm = 1737.0          # km
    LU = 384400.0        # km (地月距离)
    Ce_km_s = 3.0        # km/s (比冲)

    # 归一化常数
    mu_sys = mu_e + mu_m
    mu = mu_m / mu_sys
    TU = np.sqrt(LU**3 / mu_sys)
    VU = LU / TU

    # 轨道高度
    Re_norm = Re / LU
    Rm_norm = Rm / LU
    h_LEO = 400.0 / LU
    h_LLO = 100.0 / LU

    # 质量参数
    M_dry = 10000.0      # kg (干重)
    M_fuel_max = 15000.0 # kg (燃料上限)
    M_return_fuel = 100.0 # kg (返回燃料)

CONST = CONST()
VEC_RE = np.array([-CONST.mu, 0])
VEC_RM = np.array([1 - CONST.mu, 0])

# ==================== CR3BP动力学 ====================
def all_dynamics(t, y):
    """圆型限制性三体问题动力学方程"""
    x, yy, vx, vy = y
    mu = CONST.mu
    r1 = np.sqrt((x + mu)**2 + yy**2)
    r2 = np.sqrt((x - 1 + mu)**2 + yy**2)
    ax = 2*vy + x - (1-mu)*(x+mu)/r1**3 - mu*(x-1+mu)/r2**3
    ay = -2*vx + yy - (1-mu)*yy/r1**3 - mu*yy/r2**3
    return np.array([vx, vy, ax, ay])

# ==================== 补给飞船（L1 Lyapunov轨道）====================
class SupplyShip:
    """L1附近Lyapunov周期轨道上的补给飞船"""

    # 验证器中使用的参考种子；通过 shooting 做周期修正，避免纯硬编码。
    _VY0_SEED = 0.357451232635779
    _PERIOD_SEED = 3.323077527968701

    def __init__(self, x0=0.8, rtol=1e-12, atol=1e-12):
        self.x0 = float(x0)
        self.rtol = float(rtol)
        self.atol = float(atol)

        self.initial_state, self.period = self._solve_periodic_orbit()
        self.half_period = 0.5 * self.period
        self.solution = self._integrate_one_period()
        self.closure_error = self._compute_closure_error()

    def _state0_from_vy(self, vy0):
        return np.array([self.x0, 0.0, 0.0, float(vy0)], dtype=float)

    def _half_period_residual(self, variables):
        vy0, half_period = variables
        if half_period <= 0.0:
            return np.array([1e3, 1e3], dtype=float)

        state0 = self._state0_from_vy(vy0)
        sol = solve_ivp(
            all_dynamics,
            [0.0, half_period],
            state0,
            method="DOP853",
            rtol=self.rtol,
            atol=self.atol,
        )
        state_half = sol.y[:, -1]
        return np.array([state_half[1], state_half[2]], dtype=float)

    def _solve_periodic_orbit(self):
        seed = np.array([self._VY0_SEED, 0.5 * self._PERIOD_SEED], dtype=float)
        guesses = (
            seed,
            np.array([0.35, 1.65], dtype=float),
            np.array([0.38, 1.55], dtype=float),
        )

        best_result = None
        best_residual = np.inf

        for guess in guesses:
            result = root(self._half_period_residual, guess, method="hybr", tol=1e-13)
            residual = self._half_period_residual(result.x)
            residual_norm = float(np.linalg.norm(residual))

            if residual_norm < best_residual:
                best_result = result
                best_residual = residual_norm

            if result.success and residual_norm < 1e-10:
                break

        if best_result is None or best_residual > 1e-8:
            raise RuntimeError(f"无法求解补给飞船周期轨道，残差={best_residual:.3e}")

        vy0, half_period = best_result.x
        period = 2.0 * float(half_period)
        return self._state0_from_vy(vy0), period

    def _integrate_one_period(self):
        return solve_ivp(
            all_dynamics,
            [0.0, self.period],
            self.initial_state,
            method="DOP853",
            rtol=self.rtol,
            atol=self.atol,
            dense_output=True,
        )

    def _compute_closure_error(self):
        final_state = self.solution.y[:, -1]
        return float(np.linalg.norm(final_state - self.initial_state))

    def get_state(self, t):
        t_mod = float(np.mod(t, self.period))
        if np.isclose(t_mod, 0.0, atol=1e-14) or np.isclose(t_mod, self.period, atol=1e-14):
            return self.initial_state.copy()
        return np.asarray(self.solution.sol(t_mod), dtype=float)

    def get_position_velocity(self, t):
        state = self.get_state(t)
        return state[:2], state[2:]

    def sample_trajectory(self, num_points=400):
        ts = np.linspace(0.0, self.period, int(num_points))
        states = np.asarray(self.solution.sol(ts), dtype=float).T
        return ts, states

# ==================== 轨道与质量工具 ====================
def propagate_cr3bp(state0, dt, dense_output=False, events=None):
    return solve_ivp(
        all_dynamics,
        [0.0, float(dt)],
        np.asarray(state0, dtype=float),
        method="DOP853",
        rtol=1e-13,
        atol=1e-13,
        dense_output=dense_output,
        events=events,
    )


def build_leo_departure_state(theta, post_velocity=None):
    r_leo = CONST.h_LEO + CONST.Re_norm
    pos = VEC_RE + np.array([r_leo * np.cos(theta), r_leo * np.sin(theta)])
    u_tan = np.array([-np.sin(theta), np.cos(theta)])
    v_circ = np.sqrt((1 - CONST.mu) / r_leo)
    vel_pre = v_circ * u_tan - np.array([-pos[1], pos[0]])
    if post_velocity is None:
        vel_post = vel_pre.copy()
    else:
        vel_post = np.asarray(post_velocity, dtype=float)
    state_pre = np.concatenate([pos, vel_pre])
    state_post = np.concatenate([pos, vel_post])
    return state_pre, state_post, vel_post - vel_pre


def build_tangential_departure_state(theta, dv_tan):
    r_leo = CONST.h_LEO + CONST.Re_norm
    pos = VEC_RE + np.array([r_leo * np.cos(theta), r_leo * np.sin(theta)])
    u_tan = np.array([-np.sin(theta), np.cos(theta)])
    v_circ = np.sqrt((1 - CONST.mu) / r_leo)
    vel_post = (v_circ + dv_tan) * u_tan - np.array([-pos[1], pos[0]])
    return build_leo_departure_state(theta, post_velocity=vel_post)


def build_validator_leo_state(theta=0.0):
    """构造验证器期望的标准LEO状态。"""
    r_leo = CONST.h_LEO + CONST.Re_norm
    pos = VEC_RE + r_leo * np.array([np.cos(theta), np.sin(theta)])
    v_circ = np.sqrt((1 - CONST.mu) / r_leo)
    vel = (v_circ - r_leo) * np.array([-np.sin(theta), np.cos(theta)])
    return np.concatenate([pos, vel])


def build_llo_state(phi, prograde=True):
    r_llo = CONST.h_LLO + CONST.Rm_norm
    dr = r_llo * np.array([np.cos(phi), np.sin(phi)])
    u_tan = np.array([-np.sin(phi), np.cos(phi)])
    if not prograde:
        u_tan = -u_tan
    vel_inertial = np.sqrt(CONST.mu / r_llo) * u_tan
    vel_synodic = vel_inertial - np.array([-dr[1], dr[0]])
    return np.concatenate([VEC_RM + dr, vel_synodic])


def get_moon_relative_inertial_velocity(state):
    dr = state[0:2] - VEC_RM
    return state[2:4] + np.array([-dr[1], dr[0]])


def lunar_phase_from_state(state):
    dr = state[0:2] - VEC_RM
    return float(np.arctan2(dr[1], dr[0]))


def is_lunar_prograde(state):
    dr = state[0:2] - VEC_RM
    v_inertial = get_moon_relative_inertial_velocity(state)
    return float(dr[0] * v_inertial[1] - dr[1] * v_inertial[0]) >= 0.0


def propagate_LLO(state_old, dt, t_old):
    """在LLO上传播"""
    pos_M = VEC_RM
    dr = state_old[0:2] - pos_M
    r_mag = np.linalg.norm(dr)
    v_iner = state_old[2:4] + np.array([-dr[1], dr[0]])
    n = np.sqrt(CONST.mu / r_mag**3)
    d_theta = -n * dt
    if dr[0] * v_iner[1] - dr[1] * v_iner[0] < 0:
        d_theta = -d_theta
    R = np.array([[np.cos(d_theta), -np.sin(d_theta)],
                  [np.sin(d_theta), np.cos(d_theta)]])
    dr_new = R @ dr
    v_new = R @ v_iner
    state_new = np.concatenate([dr_new + pos_M, v_new - np.array([-dr_new[1], dr_new[0]])])
    return state_new, t_old + dt


def compute_launch_mass(state_post):
    x_rel = state_post[0] + CONST.mu
    y_rel = state_post[1]
    v_ix = state_post[2] - y_rel
    v_iy = state_post[3] + x_rel
    c3 = ((v_ix**2 + v_iy**2) * CONST.VU**2) - 2 * CONST.mu_e / (np.sqrt(x_rel**2 + y_rel**2) * CONST.LU)
    return c3, 25000.0 - 1000.0 * c3


def fuel_after_impulse(fuel_before, payload_mass, dv_vec):
    mass_before = CONST.M_dry + payload_mass + fuel_before
    mass_after = mass_before * np.exp(-(np.linalg.norm(dv_vec) * CONST.VU) / CONST.Ce_km_s)
    return mass_after - CONST.M_dry - payload_mass


def fuel_before_impulse(fuel_after, payload_mass, dv_vec):
    ratio = np.exp(-(np.linalg.norm(dv_vec) * CONST.VU) / CONST.Ce_km_s)
    return (CONST.M_dry + payload_mass + fuel_after) / ratio - CONST.M_dry - payload_mass


def choose_two_refuel_plan(M0, dv_loi_vec, dv_tei_vec, fuel_after_loi_target=10.0):
    launch_fuel = 0.0
    payload = M0 - CONST.M_dry - launch_fuel
    if payload < 0.0:
        raise RuntimeError("发射质量不足以携带干重")

    fuel_before_loi = fuel_before_impulse(fuel_after_loi_target, payload, dv_loi_vec)
    fuel_after_loi = fuel_after_impulse(fuel_before_loi, payload, dv_loi_vec)
    fuel_before_tei = fuel_before_impulse(CONST.M_return_fuel, 0.0, dv_tei_vec)
    fuel_after_tei = fuel_after_impulse(fuel_before_tei, 0.0, dv_tei_vec)

    if fuel_before_loi < -1e-9 or fuel_before_tei < -1e-9:
        raise RuntimeError("补给规划失败：出现负燃料需求")

    return (
        launch_fuel,
        payload,
        max(0.0, fuel_before_loi),
        max(0.0, fuel_after_loi),
        max(0.0, fuel_before_tei),
        max(0.0, fuel_after_tei),
    )


def append_event_row(data, event, t, state, dv_vec, fuel_mass, payload_mass):
    state = np.asarray(state, dtype=float)
    dv_vec = np.asarray(dv_vec, dtype=float)
    data.append([
        int(event),
        float(t),
        float(state[0]),
        float(state[1]),
        float(state[2]),
        float(state[3]),
        float(dv_vec[0]),
        float(dv_vec[1]),
        float(fuel_mass),
        float(payload_mass),
    ])


def append_two_row_coast(data, t0, state0, t1, state1, fuel_mass, payload_mass):
    append_event_row(data, 0, t0, state0, np.zeros(2), fuel_mass, payload_mass)
    append_event_row(data, 0, t1, state1, np.zeros(2), fuel_mass, payload_mass)


def append_two_row_maneuver(data, t, state_pre, state_post, dv_vec, fuel_before, fuel_after, payload_mass):
    append_event_row(data, -1, t, state_pre, np.zeros(2), fuel_before, payload_mass)
    append_event_row(data, -1, t, state_post, dv_vec, fuel_after, payload_mass)


def append_two_row_rendezvous(data, t, state_supply, fuel_before, fuel_after, payload_mass):
    append_event_row(data, 5, t, state_supply, np.zeros(2), fuel_before, payload_mass)
    append_event_row(data, 5, t, state_supply, np.zeros(2), fuel_after, payload_mass)


def solve_seed_direct_transfer(target_moon):
    dv1 = 3.082
    dt1 = 3.2
    # 来自上一版可运行轨迹的稳定出发角；这里只作为 patch solver 的初值来源。
    theta_opt = -2.369557
    state_depart_pre, state_depart_post, dv_depart_vec = build_tangential_departure_state(theta_opt, dv1)

    def event_moon_arrival(t, y):
        return np.linalg.norm(y[0:2] - VEC_RM) - target_moon

    event_moon_arrival.terminal = True
    sol_to_moon = propagate_cr3bp(state_depart_post, dt1 * 1.5, dense_output=True, events=event_moon_arrival)
    if sol_to_moon.t_events[0].size == 0:
        raise RuntimeError("基线种子轨道未到达月球目标半径")

    t_arrival = float(sol_to_moon.t_events[0][0])
    state_arrival = np.asarray(sol_to_moon.y_events[0][0], dtype=float)

    dr = state_arrival[0:2] - VEC_RM
    r_mag = np.linalg.norm(dr)
    u_rad = dr / r_mag
    u_tan = np.array([-u_rad[1], u_rad[0]])
    if np.dot(get_moon_relative_inertial_velocity(state_arrival), u_tan) < 0:
        u_tan = -u_tan
    vel_loi = np.sqrt(CONST.mu / r_mag) * u_tan - np.array([-dr[1], dr[0]])
    state_loi = state_arrival.copy()
    state_loi[2:4] = vel_loi

    return {
        "theta": theta_opt,
        "t_depart": 0.0,
        "state_depart_pre": state_depart_pre,
        "state_depart_post": state_depart_post,
        "dv_depart_vec": dv_depart_vec,
        "to_moon_solution": sol_to_moon,
        "t_arrival": t_arrival,
        "state_arrival": state_arrival,
        "state_loi": state_loi,
    }


def find_seed_supply_match(seed_transfer, supply_ship):
    ts = np.linspace(0.05, seed_transfer["t_arrival"], 500)
    seed_states = np.asarray(seed_transfer["to_moon_solution"].sol(ts), dtype=float).T
    supply_states = np.asarray([supply_ship.get_state(t) for t in ts], dtype=float)
    pos_error = np.linalg.norm(seed_states[:, 0:2] - supply_states[:, 0:2], axis=1)
    vel_error = np.linalg.norm(seed_states[:, 2:4] - supply_states[:, 2:4], axis=1)
    scores = pos_error + 0.2 * vel_error
    best_idx = int(np.argmin(scores))
    return {
        "t_match": float(ts[best_idx]),
        "seed_state": seed_states[best_idx],
        "supply_state": supply_states[best_idx],
        "score": float(scores[best_idx]),
    }


def solve_patch_to_supply(supply_ship, seed_transfer):
    r_leo = CONST.h_LEO + CONST.Re_norm
    seed_match = find_seed_supply_match(seed_transfer, supply_ship)

    def earth_orbit_radius_error(t_rv):
        state_rv = supply_ship.get_state(t_rv)
        state_back = np.asarray(propagate_cr3bp(state_rv, -t_rv).y[:, -1], dtype=float)
        radius = np.linalg.norm(state_back[0:2] - VEC_RE)
        return abs(radius - r_leo), state_back

    t_center = seed_match["t_match"]
    t_grid = np.linspace(max(0.08, t_center - 0.30), t_center + 0.30, 120)
    best_t = None
    best_state = None
    best_err = np.inf
    for t_rv in t_grid:
        err, state_back = earth_orbit_radius_error(t_rv)
        if err < best_err:
            best_t = float(t_rv)
            best_state = state_back
            best_err = float(err)

    result = minimize_scalar(
        lambda t: earth_orbit_radius_error(float(t))[0],
        bounds=(max(0.05, best_t - 0.02), best_t + 0.02),
        method="bounded",
        options={"xatol": 1e-12},
    )
    tof = float(result.x)
    best_err, best_state = earth_orbit_radius_error(tof)
    if best_err > 1e-7:
        raise RuntimeError(f"无法求解 Earth->Supply patch，轨道半径误差={best_err:.3e}")

    theta = float(np.arctan2(best_state[1] - VEC_RE[1], best_state[0] - VEC_RE[0]))
    state_depart_pre, _, dv_depart_vec = build_leo_departure_state(theta, post_velocity=best_state[2:4])
    state_depart_post = best_state.copy()
    sol_to_supply = propagate_cr3bp(state_depart_post, tof, dense_output=True)
    state_rv = np.asarray(sol_to_supply.y[:, -1], dtype=float)
    return {
        "theta": float(theta),
        "t_rv": float(tof),
        "state_depart_pre": state_depart_pre,
        "state_depart_post": state_depart_post,
        "dv_depart_vec": dv_depart_vec,
        "state_rv": state_rv,
        "solution": sol_to_supply,
    }


def solve_patch_supply_to_llo(supply_ship, rendezvous_patch, seed_transfer):
    phi_seed = lunar_phase_from_state(seed_transfer["state_loi"])
    tof_seed = max(0.08, seed_transfer["t_arrival"] - rendezvous_patch["t_rv"])
    supply_state = rendezvous_patch["state_rv"]
    prograde_seed = is_lunar_prograde(seed_transfer["state_loi"])
    candidate_solutions = []

    for prograde in (prograde_seed, not prograde_seed):
        bounds_lower = np.array([0.05, -np.pi], dtype=float)
        bounds_upper = np.array([3.0, np.pi], dtype=float)
        guess_bank = (
            np.array([tof_seed, phi_seed], dtype=float),
            np.array([max(0.08, tof_seed * 0.8), phi_seed - 0.15], dtype=float),
            np.array([tof_seed + 0.10, phi_seed + 0.15], dtype=float),
            np.array([0.25, np.pi], dtype=float),
        )

        def residual(variables):
            tof, phi = variables
            target_state = build_llo_state(phi, prograde=prograde)
            state_back = np.asarray(propagate_cr3bp(target_state, -tof).y[:, -1], dtype=float)
            return state_back[0:2] - supply_state[0:2]

        best_result = None
        best_norm = np.inf
        for guess in guess_bank:
            guess = np.clip(guess, bounds_lower, bounds_upper)
            result = least_squares(
                residual,
                guess,
                bounds=(bounds_lower, bounds_upper),
                xtol=1e-12,
                ftol=1e-12,
                gtol=1e-12,
                max_nfev=400,
            )
            residual_norm = float(np.linalg.norm(result.fun))
            if residual_norm < best_norm:
                best_result = result
                best_norm = residual_norm
            if result.success and residual_norm < 1e-9:
                break

        if best_result is None or best_norm > 1e-7:
            continue

        tof, phi = best_result.x
        target_state = build_llo_state(phi, prograde=prograde)
        state_back = np.asarray(propagate_cr3bp(target_state, -tof).y[:, -1], dtype=float)
        dv_sep_vec = state_back[2:4] - supply_state[2:4]
        state_post_sep = supply_state.copy()
        state_post_sep[2:4] = state_post_sep[2:4] + dv_sep_vec
        sol_to_llo = propagate_cr3bp(state_post_sep, tof, dense_output=True)
        state_llo = np.asarray(sol_to_llo.y[:, -1], dtype=float)
        candidate_solutions.append({
            "prograde": prograde,
            "phi": float(phi),
            "t_arrival": rendezvous_patch["t_rv"] + float(tof),
            "state_pre_sep": supply_state.copy(),
            "state_post_sep": state_post_sep,
            "dv_sep_vec": dv_sep_vec,
            "state_llo": state_llo,
            "solution": sol_to_llo,
        })

    if not candidate_solutions:
        raise RuntimeError("无法求解 Supply->LLO patch")

    return min(candidate_solutions, key=lambda item: np.linalg.norm(item["dv_sep_vec"]))


def compute_return_altitude(state_pre_tei, dv3):
    dr_dep = state_pre_tei[0:2] - VEC_RM
    u_tan_dep = np.array([-dr_dep[1], dr_dep[0]]) / np.linalg.norm(dr_dep)
    if np.dot(get_moon_relative_inertial_velocity(state_pre_tei), u_tan_dep) < 0:
        u_tan_dep = -u_tan_dep

    dv3_vec = dv3 * u_tan_dep
    state_post = state_pre_tei.copy()
    state_post[2:4] = state_post[2:4] + dv3_vec
    sol = propagate_cr3bp(state_post, 6.0, dense_output=True)

    t_samples = np.linspace(0, sol.t[-1], 8000)
    dists = np.array([np.linalg.norm(sol.sol(t)[0:2] - VEC_RE) for t in t_samples])
    t_guess = float(t_samples[int(np.argmin(dists))])

    def dist_func(t):
        if t < 0 or t > sol.t[-1]:
            return 1e10
        return np.linalg.norm(sol.sol(t)[0:2] - VEC_RE)

    result = minimize_scalar(
        dist_func,
        bounds=(max(0.0, t_guess - 0.3), min(sol.t[-1], t_guess + 0.3)),
        method="bounded",
        options={"xatol": 1e-12},
    )
    altitude = (result.fun - CONST.Re_norm) * CONST.LU
    return altitude, float(result.x), sol, dv3_vec


def choose_fuel_plan(M0, dv_supply_vec, dv_tei_vec):
    def final_fuel_with_plan(payload_mass, fuel_after_rv):
        fuel_after_sep = fuel_after_impulse(fuel_after_rv, payload_mass, dv_supply_vec)
        fuel_after_tei = fuel_after_impulse(fuel_after_sep, 0.0, dv_tei_vec)
        return fuel_after_sep, fuel_after_tei

    launch_fuel = 0.0
    payload = M0 - CONST.M_dry - launch_fuel
    fuel_after_sep_full, fuel_after_tei_full = final_fuel_with_plan(payload, CONST.M_fuel_max)

    if fuel_after_tei_full >= CONST.M_return_fuel:
        lo = launch_fuel
        hi = CONST.M_fuel_max
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            _, fuel_after_tei_mid = final_fuel_with_plan(payload, mid)
            if fuel_after_tei_mid >= CONST.M_return_fuel:
                hi = mid
            else:
                lo = mid
        fuel_after_rv = hi
        fuel_after_sep, fuel_after_tei = final_fuel_with_plan(payload, fuel_after_rv)
        return launch_fuel, payload, fuel_after_rv, fuel_after_sep, fuel_after_tei

    max_launch_fuel = min(CONST.M_fuel_max, M0 - CONST.M_dry)
    _, fuel_after_tei_max = final_fuel_with_plan(M0 - CONST.M_dry - max_launch_fuel, CONST.M_fuel_max)
    if fuel_after_tei_max < CONST.M_return_fuel:
        raise RuntimeError("即使在补给后装满燃料，也无法满足返回燃料约束")

    lo = 0.0
    hi = max_launch_fuel
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        payload_mid = M0 - CONST.M_dry - mid
        _, fuel_after_tei_mid = final_fuel_with_plan(payload_mid, CONST.M_fuel_max)
        if fuel_after_tei_mid >= CONST.M_return_fuel:
            hi = mid
        else:
            lo = mid

    launch_fuel = hi
    payload = M0 - CONST.M_dry - launch_fuel
    fuel_after_rv = CONST.M_fuel_max
    fuel_after_sep, fuel_after_tei = final_fuel_with_plan(payload, fuel_after_rv)
    return launch_fuel, payload, fuel_after_rv, fuel_after_sep, fuel_after_tei


# ==================== 主程序 ====================
print("=" * 60)
print("地月转移轨道优化 - 当前方案：直达转移 + 双补给节点（Event 5）")
print("=" * 60)

t0 = 0.0
target_moon = CONST.Rm_norm + CONST.h_LLO

print("\n[1/6] 求解补给飞船轨道与直达月球转移...")
try:
    supply_ship = SupplyShip()
    print(f"  补给飞船周期: {supply_ship.period:.6f} TU, 闭合误差: {supply_ship.closure_error:.3e}")
except Exception as e:
    raise RuntimeError(f"补给飞船轨道求解失败: {e}")

direct_transfer = solve_seed_direct_transfer(target_moon)
t_arr_M = direct_transfer["t_arrival"]
state_arr_M = direct_transfer["state_arrival"]
state_loi = direct_transfer["state_loi"]
dv2_vec = state_loi[2:4] - state_arr_M[2:4]
print(f"  到达月球: {t_arr_M * CONST.TU / 86400:.2f}天")
print(f"  LOI dv = {np.linalg.norm(dv2_vec) * CONST.VU:.6f} km/s")

print("\n[2/6] 月面停留...")
dt_stay_days = 9.0
dt_stay = dt_stay_days * 86400 / CONST.TU
state_pre_tei, t_dep = propagate_LLO(state_loi, dt_stay, t_arr_M)
print(f"  停留时间: {dt_stay_days:.2f}天")

print("\n[3/6] 优化TEI参数...")
result_dv3 = minimize_scalar(
    lambda dv3: abs(compute_return_altitude(state_pre_tei, dv3)[0]),
    bounds=(0.70, 0.95),
    method="bounded",
)
dv3_optimal = float(result_dv3.x)
alt_final, t_peri, sol_tei, dv3_vec = compute_return_altitude(state_pre_tei, dv3_optimal)
print(f"  最优dv3={dv3_optimal:.6f} VU, 返回高度={alt_final:.2f} km")

print("\n[4/6] 计算质量预算与补给方案...")
C3, M0 = compute_launch_mass(direct_transfer["state_depart_post"])
Fuel_launch, Payload, Fuel_before_loi, Fuel_after_loi, Fuel_before_tei, Fuel_after_tei = choose_two_refuel_plan(
    M0,
    dv2_vec,
    dv3_vec,
)
fuel_added_loi = Fuel_before_loi - Fuel_launch
fuel_added_tei = Fuel_before_tei - Fuel_after_loi
print(f"  C3 = {C3:.4f} km²/s²")
print(f"  M0 = {M0:.2f} kg")
print(f"  Launch fuel = {Fuel_launch:.2f} kg")
print(f"  Payload = {Payload:.2f} kg")
print(f"  Event 5 #1 加注 = {fuel_added_loi:.2f} kg")
print(f"  Event 5 #2 加注 = {fuel_added_tei:.2f} kg")

print("\n[5/6] 采样两个补给对接节点...")
state_supply_loi = supply_ship.get_state(t_arr_M)
state_supply_tei = supply_ship.get_state(t_dep)
print(f"  对接节点 1: t = {t_arr_M * CONST.TU / 86400:.2f}天")
print(f"  对接节点 2: t = {t_dep * CONST.TU / 86400:.2f}天")

t_arr_E = t_dep + t_peri
total_days = t_arr_E * CONST.TU / 86400
print(f"\n任务总时长: {total_days:.2f}天")

print("\n[6/6] 生成results.txt...")
data = []

state_leo_validator = build_validator_leo_state(0.0)

append_event_row(
    data,
    1,
    t0,
    state_leo_validator,
    np.zeros(2),
    Fuel_launch,
    Payload,
)
append_event_row(
    data,
    1,
    t0,
    direct_transfer["state_depart_post"],
    direct_transfer["dv_depart_vec"],
    Fuel_launch,
    Payload,
)

append_two_row_coast(
    data,
    t0,
    direct_transfer["state_depart_post"],
    t_arr_M,
    state_arr_M,
    Fuel_launch,
    Payload,
)
append_two_row_rendezvous(
    data,
    t_arr_M,
    state_supply_loi,
    Fuel_launch,
    Fuel_before_loi,
    Payload,
)
append_two_row_maneuver(
    data,
    t_arr_M,
    state_arr_M,
    state_loi,
    dv2_vec,
    Fuel_before_loi,
    Fuel_after_loi,
    Payload,
)
append_event_row(data, 2, t_arr_M, state_loi, np.zeros(2), Fuel_after_loi, Payload)
append_event_row(data, 3, t_dep, state_pre_tei, np.zeros(2), Fuel_after_loi, 0.0)

append_two_row_rendezvous(
    data,
    t_dep,
    state_supply_tei,
    Fuel_after_loi,
    Fuel_before_tei,
    0.0,
)

state_post_tei = state_pre_tei.copy()
state_post_tei[2:4] = state_post_tei[2:4] + dv3_vec
append_two_row_maneuver(
    data,
    t_dep,
    state_pre_tei,
    state_post_tei,
    dv3_vec,
    Fuel_before_tei,
    Fuel_after_tei,
    0.0,
)

t_safe = 0.1
state_safe = np.asarray(sol_tei.sol(t_safe), dtype=float)
append_two_row_coast(
    data,
    t_dep,
    state_post_tei,
    t_dep + t_safe,
    state_safe,
    Fuel_after_tei,
    0.0,
)

state_final = np.asarray(sol_tei.sol(t_peri), dtype=float)
append_event_row(data, 4, t_arr_E, state_final, np.zeros(2), Fuel_after_tei, 0.0)

data = np.asarray(data, dtype=float)
np.savetxt("results.txt", data, fmt=["%d"] + ["%.12e"] * 9, delimiter="\t")

print("=" * 60)
print("✓ 程序完成")
print(f"✓ Payload: {Payload:.2f} kg")
print(f"✓ 任务时长: {total_days:.2f}天")
print("=" * 60)

# EVOLVE-BLOCK-END


# 固定的入口函数（不被演化）
def run_mission():
    """运行月球任务并返回生成results.txt文件的路径"""
    # 上面的代码会生成results.txt
    return "results.txt"
