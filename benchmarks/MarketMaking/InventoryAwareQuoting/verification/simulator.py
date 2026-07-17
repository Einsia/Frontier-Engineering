from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping

import numpy as np


SYMBOLS = ("NVDA", "JPM", "AMZN")
POSITION_LIMIT = 50
STARTING_CASH = 100_000.0
MIN_QUOTE_RATE = 0.70
MIN_LIQUIDITY_SERVICE = 0.20
MAKER_FEE_BPS = 0.15
TAKER_FEE_BPS = 1.20
ACTION_FIELDS = frozenset({"bid_offset_bps", "ask_offset_bps", "bid_size", "ask_size"})


class ActionValidationError(ValueError):
    """A candidate-action error with a stable category for optimizer feedback."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class AssetSpec:
    start_price: float
    step_volatility: float
    primary_spread_bps: float
    dual_spread_bps: float
    fill_intensity: float


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    seed: int
    volatility_scale: float
    flow_persistence: float
    flow_bias: float = 0.0
    volatility_trend: float = 0.0
    flow_reversal: bool = False
    basis_scale: float = 1.0
    arrival_scale: float = 1.0
    feedback: bool = True


ASSET_SPECS = {
    "NVDA": AssetSpec(120.0, 0.0018, 2.0, 8.0, 0.72),
    "JPM": AssetSpec(205.0, 0.0010, 1.5, 6.0, 0.62),
    "AMZN": AssetSpec(185.0, 0.0014, 1.8, 7.0, 0.67),
}


# Public development regimes provide interpretable feedback. Validation regimes below are
# deterministic distribution shifts whose per-path details are withheld from artifacts.
SCENARIOS = (
    ScenarioSpec("calm_balanced", 4201, 0.72, 0.45),
    ScenarioSpec("calm_buy_flow", 4202, 0.80, 0.72, 0.35),
    ScenarioSpec("calm_sell_flow", 4203, 0.80, 0.72, -0.35),
    ScenarioSpec("normal_balanced", 4204, 1.00, 0.60),
    ScenarioSpec("normal_buy_flow", 4205, 1.00, 0.82, 0.45),
    ScenarioSpec("normal_sell_flow", 4206, 1.00, 0.82, -0.45),
    ScenarioSpec("volatile_balanced", 4207, 1.45, 0.58, basis_scale=1.25),
    ScenarioSpec("volatile_buy_flow", 4208, 1.35, 0.80, 0.45, basis_scale=1.20),
    ScenarioSpec("volatile_sell_flow", 4209, 1.35, 0.80, -0.45, basis_scale=1.20),
    ScenarioSpec("rising_volatility", 4210, 1.05, 0.70, volatility_trend=0.90),
    ScenarioSpec("falling_volatility", 4211, 1.15, 0.70, volatility_trend=-0.70),
    ScenarioSpec("flow_reversal", 4212, 1.10, 0.86, 0.48, flow_reversal=True),
)


VALIDATION_SCENARIOS = (
    ScenarioSpec("validation_01", 5301, 0.68, 0.32, -0.18, basis_scale=1.30, feedback=False),
    ScenarioSpec("validation_02", 5302, 0.92, 0.76, 0.28, flow_reversal=True, feedback=False),
    ScenarioSpec("validation_03", 5303, 1.22, 0.55, -0.30, basis_scale=1.35, feedback=False),
    ScenarioSpec("validation_04", 5304, 1.58, 0.68, 0.12, arrival_scale=1.15, feedback=False),
    ScenarioSpec("validation_05", 5305, 0.84, 0.90, 0.42, flow_reversal=True, feedback=False),
    ScenarioSpec("validation_06", 5306, 1.42, 0.38, -0.08, volatility_trend=-0.45, feedback=False),
    ScenarioSpec("validation_07", 5307, 1.08, 0.79, -0.44, volatility_trend=0.55, feedback=False),
    ScenarioSpec("validation_08", 5308, 1.30, 0.62, 0.0, basis_scale=1.55, feedback=False),
)

EVALUATION_SCENARIOS = SCENARIOS + VALIDATION_SCENARIOS


_REGIME_PARAMS = {
    "quiet": (0.65, 0.72, 0.60),
    "normal": (1.00, 1.00, 1.00),
    "volatile": (1.65, 1.10, 1.20),
    "toxic": (1.35, 1.30, 1.80),
}

_REGIME_TRANSITIONS = {
    "quiet": (("normal", 0.75), ("volatile", 0.20), ("toxic", 0.05)),
    "normal": (("quiet", 0.45), ("volatile", 0.40), ("toxic", 0.15)),
    "volatile": (("quiet", 0.15), ("normal", 0.60), ("toxic", 0.25)),
    "toxic": (("quiet", 0.10), ("normal", 0.55), ("volatile", 0.35)),
}


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _scenario_for_seed(seed: int) -> ScenarioSpec:
    for scenario in EVALUATION_SCENARIOS:
        if scenario.seed == seed:
            return scenario
    return ScenarioSpec("custom", int(seed), 1.0, 0.60, feedback=False)


def _weighted_choice(rng: np.random.Generator, options: tuple[tuple[str, float], ...]) -> str:
    draw = float(rng.random())
    cumulative = 0.0
    for value, weight in options:
        cumulative += weight
        if draw <= cumulative:
            return value
    return options[-1][0]


def passive_fill_probability(
    *,
    quote_edge_bps: float,
    flow_signal: float,
    side: str,
    arrival_multiplier: float,
    toxicity: float,
    fill_intensity: float,
    size: int,
) -> float:
    """Continuous passive-fill model based on competitiveness versus the DUAL book."""

    if size <= 0:
        return 0.0
    if side not in {"bid", "ask"}:
        raise ValueError("side must be bid or ask")
    toxic_flow = -flow_signal if side == "bid" else flow_signal
    logit = (
        -1.45
        + math.log(max(1e-9, arrival_multiplier * fill_intensity / 0.67))
        + 0.16 * float(np.clip(quote_edge_bps, -35.0, 20.0))
        + 0.78 * toxicity * toxic_flow
        - 0.08 * (size - 1)
    )
    return float(min(0.96, max(0.0, _sigmoid(logit))))


class DualMarketSimulator:
    """Deterministic primary/DUAL top-of-book market-making simulator.

    The complete exogenous market tape is generated before the policy runs. Candidate actions
    change fills and inventory but never the future fair value, books, regimes, or random draws.
    """

    def __init__(
        self,
        seed: int | None = None,
        steps: int = 240,
        scenario: ScenarioSpec | None = None,
    ) -> None:
        if scenario is None:
            scenario = _scenario_for_seed(4201 if seed is None else int(seed))
        self.scenario = scenario
        self.steps = int(steps)
        if self.steps <= 0:
            raise ValueError("steps must be positive")
        self.step_index = 0
        self.cash = STARTING_CASH
        self.fair = {s: ASSET_SPECS[s].start_price for s in SYMBOLS}
        self.primary_mid = dict(self.fair)
        self.dual_basis = {s: 0.0 for s in SYMBOLS}
        self.dual_mid = dict(self.fair)
        self.dual_inventory = {s: 0 for s in SYMBOLS}
        self.volatility_ema = {s: ASSET_SPECS[s].step_volatility for s in SYMBOLS}
        self.imbalance_ema = {s: 0.0 for s in SYMBOLS}
        self.fills = 0
        self.passive_fills = 0
        self.aggressive_fills = 0
        self.fees_paid = 0.0
        self.violations = 0
        self.violation_reasons: dict[str, int] = {}
        self.quoted_sides = 0
        self.total_sides = 0
        self.liquidity_service_sum = 0.0
        self.active_offset_sum = 0.0
        self.active_side_count = 0
        self.inventory_square_sum = 0.0
        self.inventory_risk_square_sum = 0.0
        self.inventory_observations = 0
        self.max_abs_inventory_seen = 0
        self.regime_path: list[str] = []
        self.equity_path = [self.equity()]
        self._tape = self._build_market_tape()

    def _build_regime_schedule(self, rng: np.random.Generator) -> list[str]:
        schedule: list[str] = []
        regime = "normal"
        while len(schedule) < self.steps:
            segment = int(rng.integers(28, 53))
            schedule.extend([regime] * min(segment, self.steps - len(schedule)))
            regime = _weighted_choice(rng, _REGIME_TRANSITIONS[regime])
        return schedule

    def _build_market_tape(self) -> dict[str, dict[str, np.ndarray]]:
        rng = np.random.Generator(np.random.PCG64(self.scenario.seed))
        self.regime_path = self._build_regime_schedule(rng)
        keys = (
            "shock",
            "flow_signal",
            "primary_noise",
            "basis_innovation",
            "ask_fill_u",
            "bid_fill_u",
            "ask_qty_u",
            "bid_qty_u",
            "arrival_multiplier",
            "toxicity",
            "volatility_multiplier",
        )
        tape = {
            symbol: {key: np.empty(self.steps, dtype=float) for key in keys}
            for symbol in SYMBOLS
        }
        flow_state = self.scenario.flow_bias
        rho = self.scenario.flow_persistence
        innovation_scale = math.sqrt(max(0.0, 1.0 - rho * rho))
        for step, regime in enumerate(self.regime_path):
            phase = step / max(1, self.steps - 1)
            regime_vol, regime_arrival, regime_toxicity = _REGIME_PARAMS[regime]
            trend_factor = 1.0 + self.scenario.volatility_trend * (phase - 0.5)
            volatility_multiplier = (
                self.scenario.volatility_scale * regime_vol * max(0.45, trend_factor)
            )
            target = self.scenario.flow_bias
            if self.scenario.flow_reversal and phase >= 0.52:
                target = -target
            flow_state = (
                rho * flow_state
                + (1.0 - rho) * target
                + innovation_scale * float(rng.normal())
            )
            common_shock = float(rng.normal())
            for symbol in SYMBOLS:
                spec = ASSET_SPECS[symbol]
                idiosyncratic = float(rng.normal())
                shock_z = 0.30 * flow_state + 0.28 * common_shock + 0.9055 * idiosyncratic
                effective_volatility = spec.step_volatility * volatility_multiplier
                shock = effective_volatility * shock_z
                flow_signal = 0.78 * flow_state + 0.72 * shock_z + float(rng.normal(0.0, 0.62))
                series = tape[symbol]
                series["shock"][step] = shock
                series["flow_signal"][step] = flow_signal
                series["primary_noise"][step] = float(rng.normal(0.0, effective_volatility * 0.05))
                basis_sigma = (
                    spec.dual_spread_bps
                    * 0.45
                    / 10_000.0
                    * self.scenario.basis_scale
                    * math.sqrt(regime_vol)
                )
                series["basis_innovation"][step] = float(rng.normal(0.0, basis_sigma))
                series["ask_fill_u"][step] = float(rng.random())
                series["bid_fill_u"][step] = float(rng.random())
                series["ask_qty_u"][step] = float(rng.random())
                series["bid_qty_u"][step] = float(rng.random())
                series["arrival_multiplier"][step] = regime_arrival * self.scenario.arrival_scale
                series["toxicity"][step] = regime_toxicity
                series["volatility_multiplier"][step] = volatility_multiplier
        return tape

    def _book(self, symbol: str, primary: bool) -> tuple[float, float]:
        spec = ASSET_SPECS[symbol]
        mid = self.primary_mid[symbol] if primary else self.dual_mid[symbol]
        spread_bps = spec.primary_spread_bps if primary else spec.dual_spread_bps
        half = mid * spread_bps / 20_000.0
        return mid - half, mid + half

    def _desk_mandate(self, symbol: str) -> str:
        """Return the human-readable operating instruction active for one asset."""

        clauses: list[str] = []
        regime = self.regime_path[self.step_index]
        if regime == "quiet":
            clauses.append("liquidity campaign: every active side must display at least 2 lots")
        elif regime == "toxic":
            clauses.append(
                "adverse-selection alert: use maker-only quotes and display at most 1 lot per side"
            )

        inventory = self.dual_inventory[symbol]
        if inventory >= 25:
            clauses.append(
                "long-inventory recovery: bid at most 1 lot and keep the ask active"
            )
        elif inventory <= -25:
            clauses.append(
                "short-inventory recovery: ask at most 1 lot and keep the bid active"
            )
        if not clauses:
            clauses.append("standard two-sided liquidity service")
        return "; ".join(clauses)

    def observation(self) -> dict[str, Any]:
        assets: dict[str, dict[str, float | int | str]] = {}
        for symbol in SYMBOLS:
            p_bid, p_ask = self._book(symbol, primary=True)
            d_bid, d_ask = self._book(symbol, primary=False)
            assets[symbol] = {
                "primary_bid": p_bid,
                "primary_ask": p_ask,
                "dual_bid": d_bid,
                "dual_ask": d_ask,
                "dual_inventory": self.dual_inventory[symbol],
                "volatility": self.volatility_ema[symbol],
                "order_imbalance": self.imbalance_ema[symbol],
                "desk_mandate": self._desk_mandate(symbol),
            }
        return {
            "step": self.step_index,
            "time_fraction": self.step_index / max(1, self.steps),
            "position_limit": POSITION_LIMIT,
            "assets": assets,
        }

    def equity(self) -> float:
        marked_positions = sum(
            self.dual_inventory[symbol] * self.dual_mid[symbol] for symbol in SYMBOLS
        )
        return float(self.cash + marked_positions)

    @staticmethod
    def _validate_action_schema(actions: Any) -> None:
        """Validate the complete shape and primitive types before checking numeric ranges."""

        if not isinstance(actions, Mapping):
            raise ActionValidationError("schema_top_level_type", "action must be a mapping")
        missing_symbols = sorted(set(SYMBOLS) - set(actions))
        if missing_symbols:
            raise ActionValidationError(
                "schema_missing_symbol", f"missing symbols: {', '.join(missing_symbols)}"
            )
        unexpected_symbols = sorted(set(actions) - set(SYMBOLS), key=str)
        if unexpected_symbols:
            raise ActionValidationError(
                "schema_unexpected_symbol",
                f"unexpected symbols: {', '.join(str(value) for value in unexpected_symbols)}",
            )
        for symbol in SYMBOLS:
            raw = actions[symbol]
            if not isinstance(raw, Mapping):
                raise ActionValidationError(
                    "schema_action_type", f"{symbol} action must be a mapping"
                )
            missing_fields = sorted(ACTION_FIELDS - set(raw))
            if missing_fields:
                raise ActionValidationError(
                    "schema_missing_field",
                    f"{symbol} missing fields: {', '.join(missing_fields)}",
                )
            unexpected_fields = sorted(set(raw) - ACTION_FIELDS, key=str)
            if unexpected_fields:
                raise ActionValidationError(
                    "schema_unexpected_field",
                    f"{symbol} unexpected fields: "
                    f"{', '.join(str(value) for value in unexpected_fields)}",
                )
            for field in ACTION_FIELDS:
                value = raw[field]
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ActionValidationError(
                        "schema_field_type", f"{symbol}.{field} must be a real number"
                    )
            for field in ("bid_size", "ask_size"):
                value = float(raw[field])
                if not math.isfinite(value) or abs(value - round(value)) > 1e-9:
                    raise ActionValidationError(
                        "schema_size_integer", f"{symbol}.{field} must be a finite integer"
                    )

    @staticmethod
    def _coerce_action(raw: Mapping[str, Any]) -> tuple[float, float, int, int]:
        bid_offset = float(raw["bid_offset_bps"])
        ask_offset = float(raw["ask_offset_bps"])
        bid_size_raw = float(raw["bid_size"])
        ask_size_raw = float(raw["ask_size"])
        values = (bid_offset, ask_offset, bid_size_raw, ask_size_raw)
        if not all(math.isfinite(value) for value in values):
            raise ActionValidationError("range_non_finite", "quote values must be finite")
        bid_size = int(round(bid_size_raw))
        ask_size = int(round(ask_size_raw))
        if not (1.0 <= bid_offset <= 80.0 and 1.0 <= ask_offset <= 80.0):
            raise ActionValidationError(
                "range_offset", "quote offsets must be in [1, 80] bps"
            )
        if not (0 <= bid_size <= 5 and 0 <= ask_size <= 5):
            raise ActionValidationError("range_size", "quote sizes must be in [0, 5]")
        return bid_offset, ask_offset, bid_size, ask_size

    def _record_violation(self, category: str) -> None:
        self.violations += 1
        self.violation_reasons[category] = self.violation_reasons.get(category, 0) + 1

    def _enforce_desk_mandate(
        self,
        symbol: str,
        action: tuple[float, float, int, int],
        candidate_bid: float,
        candidate_ask: float,
        dual_bid: float,
        dual_ask: float,
    ) -> None:
        _, _, bid_size, ask_size = action
        regime = self.regime_path[self.step_index]
        inventory = self.dual_inventory[symbol]
        if regime == "quiet" and any(size == 1 for size in (bid_size, ask_size)):
            raise ActionValidationError(
                "mandate_liquidity_size",
                f"{symbol} active sizes must be at least 2 during a liquidity campaign",
            )
        if regime == "toxic":
            if bid_size > 1 or ask_size > 1:
                raise ActionValidationError(
                    "mandate_toxic_size", f"{symbol} sizes must be at most 1 under toxic flow"
                )
            if (bid_size > 0 and candidate_bid >= dual_ask) or (
                ask_size > 0 and candidate_ask <= dual_bid
            ):
                raise ActionValidationError(
                    "mandate_maker_only", f"{symbol} must not cross the DUAL book under toxic flow"
                )
        if inventory >= 25 and (bid_size > 1 or ask_size == 0):
            raise ActionValidationError(
                "mandate_long_recovery",
                f"{symbol} must limit buying and keep selling active while long",
            )
        if inventory <= -25 and (ask_size > 1 or bid_size == 0):
            raise ActionValidationError(
                "mandate_short_recovery",
                f"{symbol} must limit selling and keep buying active while short",
            )

    @staticmethod
    def _incoming_quantity(size: int, quantile: float) -> int:
        available = 1 + min(4, int(quantile * 5.0))
        return min(size, available)

    def _record_service(self, quote_edge_bps: float, offset: float, size: int) -> None:
        if size <= 0:
            return
        self.quoted_sides += 1
        self.active_side_count += 1
        self.active_offset_sum += offset
        size_credit = min(1.0, size / 2.0)
        distance_behind_book = max(0.0, -quote_edge_bps)
        self.liquidity_service_sum += size_credit * math.exp(-distance_behind_book / 12.0)

    def _execute_buy(self, symbol: str, price: float, quantity: int, fee_bps: float) -> bool:
        fee = price * quantity * fee_bps / 10_000.0
        cost = price * quantity + fee
        if self.cash + 1e-12 < cost:
            self._record_violation("risk_cash_shortfall")
            return False
        self.cash -= cost
        self.dual_inventory[symbol] += quantity
        self.fees_paid += fee
        self.fills += quantity
        return True

    def _execute_sell(self, symbol: str, price: float, quantity: int, fee_bps: float) -> None:
        fee = price * quantity * fee_bps / 10_000.0
        self.cash += price * quantity - fee
        self.dual_inventory[symbol] -= quantity
        self.fees_paid += fee
        self.fills += quantity

    def step_quotes(self, actions: Mapping[str, Mapping[str, Any]]) -> None:
        if self.step_index >= self.steps:
            raise RuntimeError("scenario already completed")
        prepared: dict[str, tuple[float, float, int, int]] = {}
        quote_context: dict[str, tuple[float, float, float, float, float, float]] = {}
        schema_valid = True
        try:
            self._validate_action_schema(actions)
        except ActionValidationError as exc:
            schema_valid = False
            self._record_violation(exc.category)
            actions = {
                symbol: {
                    "bid_offset_bps": 80.0,
                    "ask_offset_bps": 80.0,
                    "bid_size": 0,
                    "ask_size": 0,
                }
                for symbol in SYMBOLS
            }
        for symbol in SYMBOLS:
            self.total_sides += 2
            try:
                action = self._coerce_action(actions[symbol])
                inventory = self.dual_inventory[symbol]
                if (
                    inventory + action[2] > POSITION_LIMIT
                    or inventory - action[3] < -POSITION_LIMIT
                ):
                    raise ActionValidationError(
                        "risk_position_limit", "quote could breach the position limit"
                    )
                primary_reference = self.primary_mid[symbol]
                dual_bid, dual_ask = self._book(symbol, primary=False)
                candidate_bid = primary_reference * (1.0 - action[0] / 10_000.0)
                candidate_ask = primary_reference * (1.0 + action[1] / 10_000.0)
                bid_edge = 10_000.0 * (candidate_bid / dual_bid - 1.0)
                ask_edge = 10_000.0 * (dual_ask / candidate_ask - 1.0)
                prepared[symbol] = action
                quote_context[symbol] = (
                    candidate_bid,
                    candidate_ask,
                    dual_bid,
                    dual_ask,
                    bid_edge,
                    ask_edge,
                )
                if schema_valid:
                    self._enforce_desk_mandate(
                        symbol,
                        action,
                        candidate_bid,
                        candidate_ask,
                        dual_bid,
                        dual_ask,
                    )
                # Only resting quotes provide liquidity. A marketable limit order is a taker
                # action and therefore earns neither quote-rate nor service credit.
                if action[2] > 0 and candidate_bid < dual_ask:
                    self._record_service(bid_edge, action[0], action[2])
                if action[3] > 0 and candidate_ask > dual_bid:
                    self._record_service(ask_edge, action[1], action[3])
            except ActionValidationError as exc:
                self._record_violation(exc.category)
                prepared[symbol] = (80.0, 80.0, 0, 0)
                quote_context[symbol] = (0.0, math.inf, 0.0, math.inf, -math.inf, -math.inf)

        step = self.step_index
        for symbol in SYMBOLS:
            spec = ASSET_SPECS[symbol]
            series = self._tape[symbol]
            bid_offset, ask_offset, bid_size, ask_size = prepared[symbol]
            candidate_bid, candidate_ask, dual_bid, dual_ask, bid_edge, ask_edge = (
                quote_context[symbol]
            )
            flow_signal = float(series["flow_signal"][step])
            arrival = float(series["arrival_multiplier"][step])
            toxicity = float(series["toxicity"][step])

            if bid_size > 0:
                quantity = self._incoming_quantity(bid_size, float(series["bid_qty_u"][step]))
                if candidate_bid >= dual_ask:
                    if self._execute_buy(symbol, dual_ask, quantity, TAKER_FEE_BPS):
                        self.aggressive_fills += quantity
                else:
                    probability = passive_fill_probability(
                        quote_edge_bps=bid_edge,
                        flow_signal=flow_signal,
                        side="bid",
                        arrival_multiplier=arrival,
                        toxicity=toxicity,
                        fill_intensity=spec.fill_intensity,
                        size=bid_size,
                    )
                    if float(series["bid_fill_u"][step]) < probability:
                        if self._execute_buy(symbol, candidate_bid, quantity, MAKER_FEE_BPS):
                            self.passive_fills += quantity

            if ask_size > 0:
                quantity = self._incoming_quantity(ask_size, float(series["ask_qty_u"][step]))
                if candidate_ask <= dual_bid:
                    self._execute_sell(symbol, dual_bid, quantity, TAKER_FEE_BPS)
                    self.aggressive_fills += quantity
                else:
                    probability = passive_fill_probability(
                        quote_edge_bps=ask_edge,
                        flow_signal=flow_signal,
                        side="ask",
                        arrival_multiplier=arrival,
                        toxicity=toxicity,
                        fill_intensity=spec.fill_intensity,
                        size=ask_size,
                    )
                    if float(series["ask_fill_u"][step]) < probability:
                        self._execute_sell(symbol, candidate_ask, quantity, MAKER_FEE_BPS)
                        self.passive_fills += quantity

            old_fair = self.fair[symbol]
            shock = float(series["shock"][step])
            new_fair = max(1.0, old_fair * math.exp(shock))
            realised_return = abs(new_fair / old_fair - 1.0)
            self.volatility_ema[symbol] = (
                0.92 * self.volatility_ema[symbol] + 0.08 * realised_return
            )
            self.imbalance_ema[symbol] = (
                0.80 * self.imbalance_ema[symbol] + 0.20 * math.tanh(flow_signal)
            )
            self.fair[symbol] = new_fair
            self.primary_mid[symbol] = new_fair * (1.0 + float(series["primary_noise"][step]))
            self.dual_basis[symbol] = (
                0.82 * self.dual_basis[symbol]
                - 0.22 * shock
                + float(series["basis_innovation"][step])
            )
            self.dual_mid[symbol] = new_fair * (1.0 + self.dual_basis[symbol])

            inventory = self.dual_inventory[symbol]
            self.inventory_square_sum += float(inventory * inventory)
            one_step_risk = (
                inventory
                * self.dual_mid[symbol]
                * spec.step_volatility
                * float(series["volatility_multiplier"][step])
            )
            self.inventory_risk_square_sum += one_step_risk * one_step_risk
            self.inventory_observations += 1
            self.max_abs_inventory_seen = max(self.max_abs_inventory_seen, abs(inventory))

        self.step_index += 1
        self.equity_path.append(self.equity())

    def metrics(self) -> dict[str, Any]:
        peak = self.equity_path[0]
        max_drawdown = 0.0
        for value in self.equity_path:
            peak = max(peak, value)
            max_drawdown = max(max_drawdown, peak - value)
        inventory_rms = math.sqrt(self.inventory_square_sum / max(1, self.inventory_observations))
        inventory_risk_rms = math.sqrt(
            self.inventory_risk_square_sum / max(1, self.inventory_observations)
        )
        liquidation_cost = 0.0
        for symbol in SYMBOLS:
            spec = ASSET_SPECS[symbol]
            liquidation_bps = spec.dual_spread_bps / 2.0 + TAKER_FEE_BPS
            liquidation_cost += (
                abs(self.dual_inventory[symbol])
                * self.dual_mid[symbol]
                * liquidation_bps
                / 10_000.0
            )
        return {
            "pnl": self.equity() - STARTING_CASH,
            "max_drawdown": max_drawdown,
            "inventory_rms": inventory_rms,
            "inventory_risk_rms": inventory_risk_rms,
            "max_abs_inventory": float(self.max_abs_inventory_seen),
            "terminal_abs_inventory": float(sum(abs(p) for p in self.dual_inventory.values())),
            "liquidation_cost": float(liquidation_cost),
            "quote_rate": self.quoted_sides / max(1, self.total_sides),
            "liquidity_service": self.liquidity_service_sum / max(1, self.total_sides),
            "mean_active_offset_bps": self.active_offset_sum / max(1, self.active_side_count),
            "fills": float(self.fills),
            "passive_fills": float(self.passive_fills),
            "aggressive_fills": float(self.aggressive_fills),
            "fees_paid": float(self.fees_paid),
            "violations": float(self.violations),
            "violation_reasons": dict(sorted(self.violation_reasons.items())),
        }


def quoting_objective(metrics: Mapping[str, float]) -> float:
    quote_shortfall = max(0.0, MIN_QUOTE_RATE - float(metrics["quote_rate"]))
    service_shortfall = max(0.0, MIN_LIQUIDITY_SERVICE - float(metrics["liquidity_service"]))
    return float(
        metrics["pnl"]
        - 0.55 * metrics["max_drawdown"]
        - 1.00 * metrics["inventory_rms"]
        - 0.80 * metrics["inventory_risk_rms"]
        - 1.50 * metrics["liquidation_cost"]
        - 8.0 * metrics["violations"]
        - 120.0 * quote_shortfall
        - 180.0 * service_shortfall
    )
