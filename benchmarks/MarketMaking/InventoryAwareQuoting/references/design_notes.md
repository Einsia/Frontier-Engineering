# Simulator design notes

This benchmark uses a compact offline top-of-book model rather than a full exchange. It is fast
enough for iterative optimization while preserving the central engineering trade-offs: spread
capture, DUAL-book competitiveness, adverse selection, maker/taker fees, changing liquidity,
inventory limits, drawdown, and terminal liquidation.

The high-level design was informed by:

- [ABIDES](https://github.com/abides-sim/abides), an agent-based market simulator;
- [QuantReplay](https://github.com/Quod-Financial/quantreplay), a multi-market replay engine.

No source code, data, or calibration assets were copied. This implementation is an independent,
NumPy-only synthetic model.

## Model boundary

- Primary and DUAL top-of-book prices are represented; there is no full depth or queue priority.
- Passive fills depend continuously on quote competitiveness versus the DUAL book, order flow,
  liquidity regime, toxicity, and displayed size.
- Marketable quotes execute at the DUAL opposite best and pay a taker fee. Resting fills execute at
  the submitted price and pay a smaller maker fee.
- The simulator omits network latency, exchange messages, cancellations, borrow availability,
  margin, market impact beyond displayed size, and a full financing model.
- Bounded negative DUAL inventory represents ordinary market-maker short inventory. Cash borrowing
  for long purchases is not allowed.
- Asset names are scenario labels, not real-data inputs.

## Reproducibility and validation

Every scenario uses an explicit PCG64 generator and pre-generates price shocks, regime changes,
basis innovations, arrivals, fill uniforms, and market-order sizes. Candidate and anchor policies
replay the same tape, so action-dependent random-number consumption cannot bias comparisons.

Twelve development regimes expose detailed feedback. Eight deterministic validation regimes use
different parameter combinations and expose only aggregate feedback. These validation cases reduce
feedback-driven overfitting while keeping comparisons exactly reproducible. Because the verifier is
open source, they are robustness cases rather than secret tests.

## Candidate isolation

The evaluator never imports candidate code in its own process. A persistent JSON-lines worker
receives only public observations and returns actions. It has bounded startup, per-decision, and
total runtime; candidate stdout is isolated and API/model credentials are removed from its
environment. A new worker is created for each scenario, preventing cross-scenario state leakage.

This boundary prevents Python-level mutation of the parent evaluator and live call-stack access to
the future tape. It is not an operating-system sandbox: generated code should still be treated as
untrusted and a production hosted service should add a low-privilege container, network isolation,
and host resource limits.

## Difficulty checks

Regression tests compare a tuned fixed-width/inventory-skew policy with a policy that reacts to
observed order imbalance. The adaptive policy must remain feasible and outperform the fixed policy
by a material margin. A separate test verifies that unconditional numeric quotes violate the
compositional desk mandates: quiet liquidity campaigns and toxic-flow defense impose incompatible
size requirements, while inventory recovery adds state-dependent asymmetry. This guards against
accidental changes that collapse the task back into a small grid search.

Action validation is intentionally staged. The evaluator first checks the complete action schema
(symbols, fields, and primitive types), then numeric ranges, then position and mandate constraints.
Stable violation categories are exposed in development artifacts so an optimizer can distinguish a
malformed program from a slightly out-of-range quote or an economically invalid risk decision.
