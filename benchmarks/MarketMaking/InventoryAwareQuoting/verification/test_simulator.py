from __future__ import annotations

import unittest

try:
    from verification.simulator import (
        SCENARIOS,
        SYMBOLS,
        DualMarketSimulator,
        passive_fill_probability,
    )
except ModuleNotFoundError:  # pytest invoked from the repository root
    from simulator import SCENARIOS, SYMBOLS, DualMarketSimulator, passive_fill_probability


def _quotes(offset: float, size: int) -> dict[str, dict[str, float | int]]:
    return {
        symbol: {
            "bid_offset_bps": offset,
            "ask_offset_bps": offset,
            "bid_size": size,
            "ask_size": size,
        }
        for symbol in SYMBOLS
    }


class SimulatorTests(unittest.TestCase):
    def test_same_policy_is_exactly_deterministic(self) -> None:
        first = DualMarketSimulator(scenario=SCENARIOS[3], steps=80)
        second = DualMarketSimulator(scenario=SCENARIOS[3], steps=80)
        for _ in range(80):
            action = _quotes(16.0, 2)
            first.step_quotes(action)
            second.step_quotes(action)
        self.assertEqual(first.metrics(), second.metrics())
        self.assertEqual(first.equity_path, second.equity_path)
        self.assertEqual(first.regime_path, second.regime_path)

    def test_exogenous_market_path_is_policy_independent(self) -> None:
        tight = DualMarketSimulator(scenario=SCENARIOS[7], steps=60)
        wide = DualMarketSimulator(scenario=SCENARIOS[7], steps=60)
        for _ in range(60):
            tight.step_quotes(_quotes(3.0, 3))
            wide.step_quotes(_quotes(70.0, 1))
            self.assertEqual(tight.fair, wide.fair)
            self.assertEqual(tight.primary_mid, wide.primary_mid)
            self.assertEqual(tight.dual_mid, wide.dual_mid)
        self.assertEqual(tight.regime_path, wide.regime_path)

    def test_invalid_action_is_rejected_without_trading(self) -> None:
        simulator = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        actions = _quotes(16.0, 2)
        actions["NVDA"]["bid_offset_bps"] = float("nan")
        simulator.step_quotes(actions)
        self.assertEqual(simulator.violations, 1)
        self.assertEqual(simulator.violation_reasons, {"range_non_finite": 1})
        self.assertEqual(simulator.dual_inventory["NVDA"], 0)

    def test_schema_errors_are_distinct_from_numeric_range_errors(self) -> None:
        missing = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        missing_actions = _quotes(16.0, 2)
        del missing_actions["NVDA"]["ask_size"]
        missing.step_quotes(missing_actions)
        self.assertEqual(missing.violation_reasons, {"schema_missing_field": 1})

        wrong_type = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        wrong_type_actions = _quotes(16.0, 2)
        wrong_type_actions["NVDA"]["bid_size"] = "two"  # type: ignore[assignment]
        wrong_type.step_quotes(wrong_type_actions)
        self.assertEqual(wrong_type.violation_reasons, {"schema_field_type": 1})

        unexpected_symbol = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        unexpected_symbol_actions = _quotes(16.0, 2)
        unexpected_symbol_actions[7] = unexpected_symbol_actions["NVDA"]  # type: ignore[index]
        unexpected_symbol.step_quotes(unexpected_symbol_actions)
        self.assertEqual(
            unexpected_symbol.violation_reasons,
            {"schema_unexpected_symbol": 1},
        )

        out_of_range = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        out_of_range_actions = _quotes(16.0, 2)
        out_of_range_actions["NVDA"]["bid_offset_bps"] = 81.0
        out_of_range.step_quotes(out_of_range_actions)
        self.assertEqual(out_of_range.violation_reasons, {"range_offset": 1})

    def test_semantic_mandates_require_regime_dependent_structure(self) -> None:
        quiet = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        quiet.regime_path[0] = "quiet"
        self.assertIn("liquidity campaign", quiet.observation()["assets"]["NVDA"]["desk_mandate"])
        quiet.step_quotes(_quotes(16.0, 1))
        self.assertEqual(quiet.violation_reasons, {"mandate_liquidity_size": 3})

        toxic = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        toxic.regime_path[0] = "toxic"
        self.assertIn(
            "adverse-selection alert",
            toxic.observation()["assets"]["NVDA"]["desk_mandate"],
        )
        toxic.step_quotes(_quotes(16.0, 2))
        self.assertEqual(toxic.violation_reasons, {"mandate_toxic_size": 3})

    def test_position_limit_rejects_worst_case_quote(self) -> None:
        simulator = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        simulator.dual_inventory["NVDA"] = 49
        actions = _quotes(16.0, 2)
        simulator.step_quotes(actions)
        self.assertEqual(simulator.violations, 1)
        self.assertLessEqual(abs(simulator.dual_inventory["NVDA"]), 50)

    def test_cash_shortfall_rejects_buy_without_borrowing(self) -> None:
        simulator = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        simulator.cash = 0.0
        simulator.dual_mid["NVDA"] = simulator.primary_mid["NVDA"] * 0.99
        actions = _quotes(1.0, 1)
        for symbol in ("JPM", "AMZN"):
            actions[symbol]["bid_size"] = 0
            actions[symbol]["ask_size"] = 0
        simulator.step_quotes(actions)
        self.assertEqual(simulator.dual_inventory["NVDA"], 0)
        self.assertGreaterEqual(simulator.violations, 1)

    def test_marketable_quote_executes_at_dual_top(self) -> None:
        simulator = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        simulator.dual_mid["NVDA"] = simulator.primary_mid["NVDA"] * 0.99
        _, dual_ask = simulator._book("NVDA", primary=False)
        starting_cash = simulator.cash
        actions = _quotes(1.0, 0)
        actions["NVDA"]["bid_size"] = 1
        simulator.step_quotes(actions)
        self.assertEqual(simulator.dual_inventory["NVDA"], 1)
        self.assertEqual(simulator.aggressive_fills, 1)
        self.assertLess(simulator.cash, starting_cash - dual_ask)
        self.assertEqual(simulator.metrics()["quote_rate"], 0.0)

    def test_dual_book_competitiveness_changes_fill_probability(self) -> None:
        behind = passive_fill_probability(
            quote_edge_bps=-8.0,
            flow_signal=0.0,
            side="bid",
            arrival_multiplier=1.0,
            toxicity=1.0,
            fill_intensity=0.67,
            size=2,
        )
        improving = passive_fill_probability(
            quote_edge_bps=2.0,
            flow_signal=0.0,
            side="bid",
            arrival_multiplier=1.0,
            toxicity=1.0,
            fill_intensity=0.67,
            size=2,
        )
        self.assertGreater(improving, behind * 3.0)

    def test_regime_schedule_contains_multiple_states(self) -> None:
        simulator = DualMarketSimulator(scenario=SCENARIOS[0], steps=240)
        self.assertGreaterEqual(len(set(simulator.regime_path)), 3)

    def test_wide_quotes_have_low_liquidity_service(self) -> None:
        simulator = DualMarketSimulator(scenario=SCENARIOS[0], steps=1)
        simulator.step_quotes(_quotes(80.0, 1))
        metrics = simulator.metrics()
        self.assertEqual(metrics["quote_rate"], 1.0)
        self.assertLess(metrics["liquidity_service"], 0.05)


if __name__ == "__main__":
    unittest.main()
