# Task: Inventory-Aware Quoting

## Engineering setting

A market maker posts bid and ask quotes on a less-liquid DUAL listing while a liquid primary
listing supplies a noisy fair-value reference. A competitive quote earns spread and liquidity,
but informed flow tends to trade immediately before an adverse price move. The policy must adapt
quote width, skew, and size as volatility, order flow, the DUAL book, and inventory change.

The three synthetic pairs are labelled NVDA, JPM, and AMZN. These are scenario labels only; the
benchmark contains no real market data and never connects to an exchange.

## Market simulator

Each scenario lasts 240 steps. The latent fair value follows a correlated log-price process:

```text
F[t+1] = F[t] * exp(sigma[t] * z[t])
```

Price shocks mix market-wide, asset-specific, and persistent flow components. The market switches
between quiet, normal, volatile, and toxic-liquidity regimes in deterministic pseudo-random
segments. The latent regime label is not observed directly. Its effects appear through prices,
the volatility estimate, order imbalance, liquidity, adverse selection, and a desk mandate that
states only the currently applicable operating constraints.

The primary and DUAL books share the latent fair value but have independent observation noise and
a mean-reverting DUAL basis. A candidate offset is converted into a price around the primary mid.
Its competitiveness relative to the DUAL same-side best quote drives passive fill probability.
A marketable quote that crosses the DUAL spread executes at the DUAL opposite best price and pays
a taker fee; passive fills execute at the candidate price and pay a smaller maker fee.

All shocks, regime transitions, basis innovations, arrivals, fill uniforms, and market-order sizes
are generated before the policy starts. Candidate and anchor therefore replay the identical
exogenous tape. Policy actions change fills, cash, and inventory, but never future randomness.

## Evaluation regimes

The evaluator uses 20 deterministic regimes:

- 12 development regimes with detailed per-regime feedback;
- 8 validation regimes containing new combinations of volatility, persistent/reversing flow,
  DUAL basis variation, and arrival intensity.

Validation paths contribute fully to feasibility and score, but expose only aggregate feedback.
This tests robustness beyond the paths used for detailed iteration feedback while preserving exact
reproducibility and fair comparisons between agents. The verifier is open source, so this is not a
claim of cryptographically hidden test data.

## Observation

`decide_quotes(observation)` receives:

- `step`, `time_fraction`, and `position_limit`;
- for every asset: `primary_bid`, `primary_ask`, `dual_bid`, and `dual_ask`;
- current `dual_inventory`;
- an exponentially weighted `volatility` estimate;
- an exponentially weighted `order_imbalance` in `[-1, 1]`.
- a per-asset natural-language `desk_mandate`, composed from instructions such as liquidity
  support, adverse-selection defense, and inventory recovery.

The policy must translate these mandates into quote behavior. A fixed numeric action cannot satisfy
all combinations: a liquidity campaign requires at least two lots on every active side, while an
adverse-selection alert caps active sides at one lot and requires maker-only quotes. Inventory
recovery instructions add asymmetric limits. The current regime label, scenario name, seed, future
prices, future flow, and fill random numbers are not present in the observation.

## Action interface

Implement in `scripts/init.py`:

```python
def decide_quotes(observation) -> dict:
    ...
```

Return one action per base symbol:

- `bid_offset_bps`, `ask_offset_bps`: distance from the primary mid in `[1, 80]` basis points;
- `bid_size`, `ask_size`: integer displayed size in `[0, 5]`.

A zero size disables that side for the step. `reset_policy()` is optional because evaluation uses a
fresh worker process for every scenario. Policies must be deterministic and JSON-serializable.

## Candidate process boundary

Candidate code is imported in a separate persistent worker. On every step the parent evaluator
sends only the public observation and receives a JSON action. Import, each decision, and total
scenario runtime are bounded. Candidate stdout is isolated and model/API credentials are removed
from its environment. This blocks mutation of the parent scoring process and live call-stack access
to the future tape. It is not a general operating-system sandbox against hostile native code.

## Hard feasibility constraints

- Every DUAL inventory must remain in `[-50, 50]`.
- Every required symbol and field must be present and finite.
- Sizes must be integers (booleans are rejected); offsets and sizes must stay in range.
- Every active desk mandate must be respected. Liquidity campaigns require active sizes of at
  least 2; adverse-selection alerts require maker-only sizes of at most 1; inventory recovery
  limits the inventory-increasing side and keeps the reducing side active.
- At least 70% of quote sides must be active in every scenario.
- Liquidity service must be at least 0.20 in every scenario. Service rewards displayed size and
  decays with distance behind the current DUAL best quote.
- The account starts with 100,000 cash units. A buy that requires borrowed cash is rejected.
- Bounded negative inventory is allowed as ordinary market-maker short inventory. Securities
  borrowing, margin, and financing costs are deliberately outside this simulator.

Any hard-constraint failure sets `valid=0` and the ranking `combined_score=0`. A separate
`diagnostic_score` remains continuous so an optimizer can see whether an invalid design improved.
Artifacts report categorized violation counts such as `schema_missing_field`, `range_offset`,
`mandate_maker_only`, and `risk_position_limit`, so structural and numeric failures remain distinct.

## Objective and score

For each scenario, the economic objective is:

```text
J = PnL
    - 0.55 * maximum_drawdown
    - 1.00 * inventory_RMS
    - 0.80 * inventory_risk_RMS
    - 1.50 * terminal_liquidation_cost
    - violation_and_service_shortfall_penalties
```

PnL already includes maker/taker fees and marks DUAL inventory at the DUAL mid. The inventory-risk
term scales positions by price and current step volatility. Terminal liquidation uses the DUAL
half-spread plus taker fee.

The candidate is compared with a fixed feasible 18-bps anchor on the identical tape. A smooth
`tanh` map produces each scenario score in `[0, 100]`, with the anchor at 50. The continuous
diagnostic score is:

```text
diagnostic_score = 0.75 * mean(scenario_scores)
                 + 0.25 * percentile20(scenario_scores)
```

This rewards average quality while retaining pressure on weak regimes. If and only if all 20
scenarios are feasible, `combined_score = diagnostic_score`; otherwise `combined_score = 0`.
Higher is better.

A strong policy must use executable feedback to discover competitive DUAL quoting, inventory
skew, flow response, volatility-aware width/size, and robust behavior across regime changes. This
synthetic benchmark is not an execution recommendation or investment product.
