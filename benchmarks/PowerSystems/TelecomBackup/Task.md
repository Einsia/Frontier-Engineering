# Regional Backup-Power Scheduling (TelecomBackup)

## Task overview

When an outage hits a region, you are given each base station's (site's) backup energy, power
draw, and coverage relationships. You must set a **time-sequenced on/off schedule for every power
supply** that **maximizes the region's total backup time** subject to the constraint that the
fraction of well-covered grid cells stays **≥ 80% at every moment**.

This is a constrained scheduling/optimization problem: the coverage constraint makes the solution
space enormous, so the goal is to produce the best schedule you can within a fixed solve-time
budget.

## Instance input

The evaluation passes one instance JSON (its path is a command-line argument) containing:

| Field | Meaning |
| --- | --- |
| `seed` | The instance's generation seed (identifies the instance). |
| `grid` | Region 200 m × 200 m, rasterised into nx × ny cells (default 20 × 20 = 400). |
| `sites` | Site coordinates (N sites). |
| `groups` | Power-supply grouping: each supply manages a group of sites (K supplies; each group shares one battery). |
| `battery` | Energy per battery (kWh). |
| `demand` | Per-cell demand (relative load unit, 0–1). |
| `pt_dbm / n_exp / threshold` | Coverage parameters: Pt = 20 dBm, path-loss exponent n = 6, threshold −105 dBm. |
| `coverage_ratio` | Coverage-constraint ratio, 0.8. |
| `delta_min` | Slot length, 5 minutes. |
| `horizon` | Total number of slots, 96 (= 8-hour planning period). |
| `site_cap` | Site rated capacity (used to normalise load). |

## Rules (scoring-simulator semantics)

- **Coverage**: the level site *s* provides to cell *g* is
  `P(g,s) = pt_dbm - 10*n_exp*log10(d(g,s)+1)` (dBm, *d* in metres). A cell attaches to the
  **strongest live site** (live = its supply is on and its battery is not depleted); a cell is
  "well covered" iff its level is > −105 dBm.
- **Power draw**: a site's working draw is `p_work_base + p_work_coef*min(load_s/site_cap, 1.0)` kW
  (load_s is the sum of the demands of the cells it covers, so it is load-dependent; the current
  instances use `p_work_base=3.0, p_work_coef=3.0`). A site's silent draw is **`p_silent`** kW
  (current instances use `p_silent=0.05`; when a supply is off its sites go silent — they provide
  no coverage but still draw silent power). The power parameters come with each instance (see the
  instance JSON and the README).
- **Load migration**: turning a supply off → its sites go silent → the cells they covered
  **immediately** attach to the strongest live site → that site's load and power draw rise.
- **Energy**: supply *k* drains `Δt × Σ(site draws)` per slot; when its energy ≤ 0 the supply
  stops (no draw, no coverage).
- **Backup time**: simulate forward from slot 0; the backup endpoint is the moment just before the
  first slot in which the fraction of well-covered cells drops below 80%. If it survives the whole
  horizon, backup time = horizon × 5 minutes.

## Decision output (the format your program must print)

Run as `python baseline/solver.py <instance.json>` and print a single JSON object to **stdout**:

```json
{"on": [
  [[0, 96]],                  // supply 0: on the whole time
  [[0, 40], [60, 96]],        // supply 1: on during 0..39 and 60..95
  []                          // supply 2: never on
]}
```

- `on[k]` is the list of **on-interval**s for supply *k*, each a half-open interval `[a, b)`
  (0-indexed, 0 ≤ a ≤ b ≤ horizon).
- Supply *k* is on in slot *s* iff some interval satisfies `a ≤ s < b`. Adjacent/overlapping
  intervals are merged, so ordering mistakes are harmless.
- `[[0, horizon]]` = on the whole time (the simplest legal solution); `[]` = never on.
- **Malformed output, out-of-range intervals, crashes, or timeouts → 0 points for that instance**
  (the simulator validates every schedule).

## Evaluation and scoring

- Instance pool: **official** evaluation scores **only runtime-generated instances**
  (anti-hardcoding); a `local` development mode scores the 8 committed fixed instances
  (N = 20..40, K = 6..12).
- Score = the **mean** backup time (minutes) over the scored instances.
- Each instance gets a fixed solve-time budget (default **60 s**); a timeout scores 0 for it.
- The budget is configurable: `--time-budget 300` (10 min) / `60` (1 min) / `10` (10 s) — a tighter
  budget usually means a lower score.

Local runs:

```powershell
python verification/evaluate.py baseline/solver.py --local                              # fixed 8 instances
python verification/evaluate.py baseline/solver.py --local --time-budget 10
python verification/evaluate.py baseline/solver.py --local --generate-seed 42            # fixed 8 + 8 generated
```

For the framework (unified) evaluation, `frontier_eval/eval_command.txt` selects
`TELECOM_EVAL_MODE=official`, so the score is computed on freshly generated instances and the
generation seed is **mandatory** (missing → explicit error, never a silent fall-back to the public
instances). Supply a **non-public** seed per run and raise the framework timeout so the full
per-instance budget fits:

```powershell
$env:TELECOM_EVAL_GENERATE_SEED = "<non-public SEED>"
python -m frontier_eval task=unified task.benchmark=PowerSystems/TelecomBackup algorithm.iterations=0 `
  algorithm.evaluator.timeout=1200 "task.runtime.shell=<path to Git Bash>"
```

To reproduce the documented reference score, score the bundled reference solver with the explicit
bypass (the integrity checks reject it: it has no EVOLVE-BLOCK region and it contains a token the
validator forbids):

```powershell
python verification/evaluate.py verification/ref_solver.py --reference --local   # -> 271.25
```

### Integrity / anti-cheating (threat model)

- **Runtime-generated instances**: in official mode the evaluator generates fresh instances at
  evaluation time (they exist only in a temp dir, never in the repo or the sandbox), so a candidate
  cannot pre-position solutions for them. Public fixed instances are not scored officially.
- **Candidate env stripping**: the candidate subprocess environment strips `FRONTIER_*` and
  `TELECOM_EVAL_*`, closing the side channel that would let it locate the evaluation baseline.
- **Static checks**: before scoring, the candidate is checked for the EVOLVE-BLOCK markers and for
  byte-identity of the code outside them (vs the initial baseline), forbidden imports of the
  evaluation/generation modules, absolute paths, and per-instance hardcoding; the same instance
  must produce identical output across two runs (determinism probe). Any violation scores 0.
- **Honest note**: in process mode the candidate has host filesystem access (a framework
  limitation); this benchmark relies on the layered defenses above, and `verification/simulator.py`
  is intentionally exposed as a white-box scorer for candidate-side search.

## Reference scores (measured)

| Strategy | Mean backup time |
| --- | --- |
| baseline (naive always-on, no scheduling) | **176.2** min |
| agent (AB-MCTS, 15 iterations, best saved program) | **266.9** min (+51%) |
| reference heuristic (`verification/ref_solver.py`, multi-rest rotation) | **271.2** min (+54%) |
| agent (ShinkaEvolve, 15 generations, best generation program) | **312.5** min (+77%) |
| agent (openevolve, 25 iterations, best saved program) | **414.4** min (+135%) |
| horizon (upper bound if coverage never drops below 80%) | 480 min |

The baseline only runs "always on" (highest coverage but the batteries drain in parallel);
`ref_solver.py`'s multi-rest rotation staggers the discharge and substantially extends backup time;
the three agent frameworks all discover schedules that beat always-on given enough iterations, and
openevolve at 25 iterations finds a near-horizon **minimum-covering-subset rotation** (surpassing
the simple reference heuristic by 53%). Instances are calibrated (silent power is cheap, working
power is expensive) and the generator guarantees a reproducible stagger-over-always-on gain of
≥ 25% per instance (measured **+27.9% .. +119.0%, mean +57.5%** — note this is the generator's
*acceptance* headroom, a different quantity from the reference solver's +54% over the baseline).

> Note: agent scores are for the **saved programs run directly**, and must be re-evaluated **from
> inside the task directory** — candidate solvers resolve `verification/simulator.py` relative to
> their own location, so running a saved program from an arbitrary path silently degrades it to the
> always-on fallback (an artificially low score). ShinkaEvolve's "saved best" understates its best
> generation (a framework tracking issue); its highest-scoring generation is used instead.
> ShinkaEvolve's 25-generation run once produced a higher score (~409) but as a **time-budgeted
> simulated annealer that is non-deterministic**, which fails the determinism probe, so it does not
> count (the valid best is 312.5 from the 15-generation run).
> At 5–15 iterations agents mostly plateau near the baseline; more iterations let them search more
> thoroughly — this task rewards exhaustive in-simulator search.

## Optimization hints

1. The backup endpoint is almost always caused by a supply depleting and coverage dropping below
   the bar — the strategy is essentially to **stagger the batteries' discharge**.
2. Coverage is **redundant** (the 80% constraint is far below full-on coverage), so you can rotate
   some supplies to rest (saving silent power) as long as coverage stays ≥ 80% at all times.
3. Load migrates when a supply is turned off, raising the remaining sites' draw — so rotation
   groups should be **geographically close** (same cluster in one group), otherwise one group may
   fail to cover its area.
4. You may `import verification/simulator.py` (read-only) inside your solver to evaluate candidate
   schedules' backup time and run a "generate–simulate–improve" search within the budget.
5. Make sure the output is **always legal** first (better fully-on than malformed), then optimize.
