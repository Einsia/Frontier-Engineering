# Optimize a complete multi-truck loading plan
Read the supplied campaign instance in environment/data/campaign:
input_items.csv, input_trucks.csv, input_parameters.csv. These are semicolon-separated
CSV files; numeric decimal commas may occur. Do not modify these input files.
The complete constraint specification is environment/RULES.txt (also RULES.pdf). Read it,
including constraints I1-I5, S1-S7, P1-P4 and all weight/axle restrictions, before coding.
This includes all of the documented loading and routing constraints.
Deliver every input item quantity by assigning items to compatible stacks and trucks;
respect delivery windows, route/supplier/plant compatibility, stackability and nesting,
orientation, dimensions, nonoverlap, unloading order, vehicle weight and axle loads.
Do not omit items.

Write three semicolon-separated CSV files under the output directory supplied on the command line, with one header row:
output_items.csv:
Item ident;Id truck;Id stack;Item code;X origin;Y origin;Z origin;X extremity;Y extremity;Z extremity
output_stacks.csv:
Id truck;Id stack;Stack code;X origin;Y origin;Z origin;X extremity;Y extremity;Z extremity
output_trucks.csv:
Id truck;Loaded length;Weight of loaded items;Volume of loaded items;EMm;EMr

Include one item row per physical unit (so Item ident repeats for input quantities).
Use unique stack identifiers and consistent truck/stack references. Item code and
Stack code are display labels; they do not replace the input Item ident.
Coordinates/dimensions are integer millimeters. Loaded length is integer millimeters,
weight/axle loads are kg, and volume is cubic meters. Numerical fields can use decimal
points or commas. Compute the truck summaries consistently with the specified formulas.
A planned truck keeps its input identifier P<suffix>. An extra copy uses Q<suffix>_<unique-copy-number>,
referring to the matching P<suffix>. Extra trucks are permitted by the supplied rules;
their transportation and inventory costs count toward the objective.

The bundled Java checker validates the full output. The evaluator rejects
outputs with constraint errors. Minimize the total transportation plus inventory cost.
No saved solution CSVs or commercial solver is supplied.



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
