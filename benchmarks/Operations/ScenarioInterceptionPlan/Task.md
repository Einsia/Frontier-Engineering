# Choose detection assays that intercept every listed incident scenario

Read `environment/data/campaign.json`. Each option is an assay. Each scenario lists the assays that detect it. Every scenario must contain at least one selected assay. Repeated scenarios must also be covered.

Minimize the number of selected options. All options have unit cost. Save exactly one JSON object with a `selected` array of distinct option identifiers to `the output directory supplied on the command line/selection.json`. Identifiers must come from the input. No other fields are needed.

The objective is the exact integer number of selected assays. Feasibility is mandatory; lower counts are better.

The order of `options` defines the stable index order used by the optional conversion helper at `environment/tools/format.py`. You may use any optimization method. There are no hidden constraints or hidden additional instances.

## Candidate interface and scoring

Edit only the EVOLVE-BLOCK in `scripts/init.py`. The evaluator invokes it as
`python scripts/init.py DATA_DIR OUTPUT_DIR ASSETS_DIR` in a fresh restricted
workspace. DATA_DIR contains the released input files, OUTPUT_DIR is writable,
and ASSETS_DIR supplies read-only baseline source/tools. Use input-derived
identifiers and regenerate outputs on every run; do not embed saved solutions.
Candidates can replace the algorithm completely within the editable block.

Every feasible result receives continuous `combined_score = -objective`; higher
is better. There is no hidden acceptance threshold. Invalid, missing, timed-out
or nonfinite results receive `valid=false` and `combined_score=-1e18`. The
evaluator independently recomputes feasibility and objective, ignoring candidate
score claims. The candidate has 900 seconds including compilation, 16 GiB
address-space limit, and no network or access to the verifier.
Use fixed seeds, stable tie-breaking and deterministic work budgets.
