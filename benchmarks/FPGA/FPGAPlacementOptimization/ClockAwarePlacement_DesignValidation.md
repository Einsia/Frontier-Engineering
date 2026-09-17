# Clock-Aware FPGA Placement — Design Validation Report

> **Purpose**: Verify design assumptions against source code before implementation  
> **Date**: 2026-07-09  
> **Scope**: aug-elfPlace baseline, ISPD benchmark data, Frontier-Engineering patterns

---

## Question 1: Where is the "Clock-Aware" part of the benchmark?

### Investigation Method

Searched exhaustively across:
- All Python source files (dreamplacefpga/) for "clock", "clk", "Clock", "CLK"
- All C++ source files (ops/place_io/src/) for "clock", "clk", "Clock", "CLK"
- All benchmark .scl files (36 files) for clock region definitions
- All benchmark .lc files for clock constraints
- All benchmark .lib files for clock pin definitions
- The Limbo bookshelf parser for clock region grammar
- The Python bindings (PybindPlaceDB.cpp) for clock region exposure

### Finding 1: Clock Pin Metadata Exists (in .lib files)

The `.lib` file defines which pins are clock pins:
```
CELL FDRE
  PIN C INPUT CLOCK
  ...
```

This is parsed by the C++ PlaceDB and stored in `LibCell.m_clkPins`.  
**Location**: `PlaceDB.cpp:805-813` (`add_clk_pin`), `LibCell.h:107-109` (`clkPinArray`)

**But**: This information is NEVER used in the placement optimization. It is only stored as metadata.

### Finding 2: Clock Region Parsing Infrastructure Exists (Dead Code)

The `BookshelfDriver.h` defines callback interfaces for parsing clock regions from the `.scl` file:
```
void initClockRegionsCbk(int xReg, int yReg);   // BookshelfDriver.h:131
void addClockRegionCbk(string const&, int, int, int, int, int, int);  // :133
```

The `PlaceDB.h` has a full data structure and methods:
```
struct clk_region { int xl, yl, xm, ym, xh, yh; };   // PlaceDB.h:26-34
vector<clk_region> m_clkRegionDB;                       // PlaceDB.h:512
vector<string> m_clkRegions;                            // PlaceDB.h:513
int m_clkRegX, m_clkRegY;                               // PlaceDB.h:514-515
void resize_clk_regions(int xReg, int yReg);            // PlaceDB.cpp:707-711
void add_clk_region(string const&, int, int, int, int, int, int);  // :713-723
```

**Location**: `PlaceDB.cpp:707-723`, `PlaceDB.h:26-34,475-476,512-515`

**Critical finding**: 
1. The PybindPlaceDB binding explicitly comments out clock region exposure:
   `PybindPlaceDB.cpp:29: //PYBIND11_MAKE_OPAQUE(std::vector<clk_region>);`
2. No Python code references `m_clkRegionDB`, `m_clkRegions`, `m_clkRegX`, or `m_clkRegY`
3. The clock region data STRUCTURE exists in C++ but is **never exposed to the Python layer**

### Finding 3: No Benchmark Contains Clock Regions

**ALL 36 benchmark .scl files were checked** (12 ISPD2016 + 22 Titan23 + 1 test + 1 example).  
**NONE** contain `CLOCKREGION` or `clock_region` definitions.

The .scl files contain only: `SITE`, `RESOURCES`, `SITEMAP` sections.

### Finding 4: The Only Clock-Aware Code is FF Control Signal Compatibility

The only operational "clock awareness" in the placer is during **LUT/FF legalization**:
- `FFSLICE HALF CLK 1` in .scl: "1 clock signal available per half-SLICE"
- This constrains which FFs can share a slice based on clock signal compatibility
- Implemented in `lut_ff_legalization.py:240` and C++ `lut_ff_legalization.cpp`
- This is about **slice packing legality**, NOT about clock distribution or clock region constraints

### Finding 5: Clock-Aware Net Weights Are Not Used

`PlaceDB.py` initializes all net weights to 1.0 (line 333):
```python
self.net_weights = np.array(np.ones(len(self.net_names)), dtype=self.dtype)
```
The `.wts` file is typically empty. There is no special weighting for clock nets.

### Conclusion for Question 1

**The "Clock-Aware" part of the benchmark is essentially non-existent in the baseline.**

What exists:
- ✅ Clock pin metadata parsing (stored but unused)
- ✅ Clock region parsing infrastructure (dead code, never exposed to Python)
- ✅ FF clock signal compatibility legalization (operational, but about slice packing, not clock distribution)

What does NOT exist:
- ❌ Clock region constraints in any benchmark file
- ❌ Clock-aware optimization objectives or constraints
- ❌ Clock skew minimization or timing-driven placement
- ❌ Clock distribution network modeling

The benchmark name "ClockAwarePlacement" is aspirational — it describes what the benchmark *should* test, not what the baseline currently implements.

---

## Question 2: Is "Clock is a hard validation gate" supported?

### Investigation Method

Searched for:
- `clock.*legal|legal.*clock|clock.*valid|clock.*constraint|clock.*region.*check`
- `check.*clock|clock.*gate|clock.*domain.*violat`
- Any validation, assertion, or exit related to clock constraints

### Result

**NO CLOCK LEGALITY CHECKING FOUND ANYWHERE IN THE CODEBASE.**

No function, no assertion, no validation warning, no exit condition related to clock legality exists. The `clk_region` data structure is parsed but never used for any purpose — not for validation, not for optimization, not for reporting.

### Evidence

- `PlaceDB.py`: Zero references to `clk_region`, `m_clkRegion`, or `clockRegion`
- `NonLinearPlace.py`: Zero references to clock in any stopping criterion, validation, or logging
- `EvalMetrics.py`: Zero clock-related metrics
- All legalization code: FF control signal compatibility is checked, but this is about **which FFs can share a slice based on control signals**, not about clock region legality
- `BasicPlace.py`: Zero clock-related validation

### Conclusion for Question 2

**This assumption is unsupported.** There is literally zero code in the baseline that validates or enforces clock constraints. Adding such a gate would require:
1. Defining clock region constraints (as new input data — no benchmark has this)
2. Implementing a clock legality checker
3. Integrating it into the evaluator

---

## Question 3: How is HPWL actually used?

### Finding 1: HPWL vs Weighted-Average Wirelength (Separation)

The codebase distinguishes between **two wirelength metrics**:

| Metric | Op | Used for | Differentiable? |
|--------|-----|----------|-----------------|
| **Weighted-Average Wirelength** | `weighted_average_wirelength` | **Optimization objective** (`PlaceObj.obj_fn`) | ✅ Yes (smooth surrogate) |
| **HPWL** | `hpwl` | **Reporting & stopping criteria** (`EvalMetrics`, `NonLinearPlace`) | ❌ No (subgradient only) |

**Evidence**:
- `PlaceObj.py:166`: `self.op_collections.wirelength_op = build_weighted_average_wl()`
- `PlaceObj.py:439`: `wirelength = self.op_collections.wirelength_op(pos)` in objective function
- `BasicPlace.py:495`: `self.op_collections.hpwl_op = self.build_hpwl()` — separate op
- `NonLinearPlace.py`: Evaluates hpwl via `eval_ops = {"hpwl": self.op_collections.hpwl_op, ...}`

### Finding 2: What the optimizer actually minimizes

The objective function (`PlaceObj.obj_fn`, line 439-449):
```python
wirelength = self.op_collections.wirelength_op(pos)  # weighted average wirelength
density = self.op_collections.fence_region_density_merged_op(pos)
density = density * (1 + quad_penalty_coeff * density)
result = wirelength + self.density_weight_u.dot(density)
```

The optimizer minimizes: **Weighted-Average Wirelength + Density-Weighted Electric Potential**

Weighted-average wirelength is a smooth approximation of HPWL where pin contributions are weighted by Gaussian kernels controlled by the `gamma` parameter. As `gamma → 0`, weighted-average wirelength → HPWL.

### Finding 3: How HPWL is used

HPWL is used for:
1. **Reporting metric** — logged every iteration via `EvalMetrics`
2. **Stopping criteria** — `Lgamma_stop_criterion` checks if HPWL increases after overflow is low
3. **Density weight update** — RePlAce algorithm compares HPWL change against bounds to adjust density weight
4. **Output** — reported as the primary quality metric in logs

### Finding 4: ISPD Contest Ranking

The ISPD 2016 FPGA contest does not define a single composite score. Based on the README and `BenchMetrics.cpp`, the primary quality metrics reported are HPWL and design statistics. The contest evaluated placers on:
- Wirelength (HPWL)
- Legality (all instances at valid sites)
- Runtime

### Conclusion for Question 3

The assumption "Score = -HPWL" is **partially correct**:

✅ HPWL is the primary quality metric for ranking  
⚠ The optimizer does NOT minimize HPWL directly — it minimizes a smooth surrogate (weighted-average wirelength)  
✅ HPWL is used in reporting and evaluation  
⚠ There is no single composite "score" in the baseline — the metrics are multi-dimensional  

For a Frontier-Engineering benchmark:
- `combined_score` = `-HPWL` is a reasonable design choice for fully legal solutions
- But this should be documented as: HPWL is the **reported quality metric**, not the exact optimization target

---

## Question 4: Audit of Previous Design Report Decisions

### Decision: "The benchmark is about clock-aware placement"

| Verdict | Evidence |
|---------|----------|
| ⚠ Partially supported | The benchmark NAME implies clock awareness, but the baseline has NO clock-aware optimization |
| | Clock pin metadata exists but is unused |
| | Clock region parsing infrastructure is dead code |
| | The only operational clock-related code is FF control signal sharing in legalization |

**Recommendation**: Either:
1. Rename the benchmark to remove "ClockAware" (becomes "FPGAPlacement")
2. Or explicitly DESIGN clock-aware constraints as a new contribution (not extracting from baseline)

### Decision: "Clock is a hard validation gate (G4)"

| Verdict | Evidence |
|---------|----------|
| ❌ Unsupported assumption | No clock legality checking exists anywhere in the codebase |
| | No benchmark file contains clock region constraints |
| | Adding this requires new constraint definitions AND new validation code |

**Recommendation**: Drop G4 as a hard gate from initial design. If the benchmark is to be clock-aware, clock constraints must be designed from scratch.

### Decision: "Score = -HPWL"

| Verdict | Evidence |
|---------|----------|
| ⚠ Partially supported | HPWL IS the primary quality metric for reporting and ranking ✅ |
| | But the optimizer minimizes WEIGHTED-AVERAGE wirelength, not HPWL ❌ |
| | No single composite "score" exists in the baseline ⚠ |

**Recommendation**: 
- `combined_score = -HPWL` is acceptable for the benchmark scoring
- Document clearly that this is the evaluation metric, distinguishing it from the optimization proxy
- Consider normalizing by baseline HPWL for cross-design comparability

### Decision: "Alternative C: Output-based scoring (evaluator only scores, doesn't run placer)"

| Verdict | Evidence |
|---------|----------|
| ✅ Verified by source | HPWL computation requires only pin positions + netlist topology |
| | EvalMetrics already computes HPWL without re-running placement |
| | The hpwl.cpp algorithm is straightforward (max-min per net) |
| | Pure-Python HPWL = ~8 lines of NumPy |

**Recommendation**: This is the correct approach. The evaluator can independently compute HPWL from a candidate's output .pl file.

### Decision: "Clock constraint files (.clk) need to be created"

| Verdict | Evidence |
|---------|----------|
| ❌ Unsupported assumption | No benchmark data contains clock region information |
| | Creating .clk files would be designing entirely new benchmark data |
| | The Bookshelf parser supports clock regions, but no parser binds them to Python |

**Recommendation**: If clock constraints are desired, this is a **greenfield design effort**, not an extraction from existing code. Consider whether the benchmark should be clock-aware at all, given the complexity.

### Decision: "Four hard validation gates (site-type, capacity, carry-chain, clock-region)"

| Verdict | Evidence |
|---------|----------|
| ✅ Site-type: Supported | PlaceDB enforces site-type mapping; legalization checks compatibility |
| ✅ Capacity: Supported | LUT/FF packer enforces per-slice resource capacity |
| ✅ Carry-chain: Supported | `lut_ff_legalization.py` has `carry_chain_checker()` |
| ❌ Clock-region: Unsupported | No clock legality code exists |

**Recommendation**: Implement only 3 gates initially (G1-G3). Add G4 only if clock constraints are designed and implemented.

### Decision: "Use ISPD 2016 benchmarks (12 designs)"

| Verdict | Evidence |
|---------|----------|
| ✅ Verified | 12 ISPD 2016 benchmarks exist under `benchmarks/ispd2016/FPGA01-FPGA12` |
| | These use the .lc file format with legality constraints |
| | Titan23 benchmarks also available (Stratix-IV architecture) |

**Recommendation**: Use ISPD 2016 as primary benchmark suite. Add Titan23 as secondary/optional.

### Decision: "aug-elfPlace is the baseline placer"

| Verdict | Evidence |
|---------|----------|
| ✅ Verified | aug-elfPlace IS the baseline, available under `baseline/aug-elfPlace/` |
| | aug-elfPlace is itself a fork of DREAMPlaceFPGA |
| | The reference implementation should be the aug-elfPlace pipeline, not DREAMPlaceFPGA alone |

### Decision: "C++ compilation dependency is a risk"

| Verdict | Evidence |
|---------|----------|
| ✅ Verified by source | All ops require C++ compilation (CMake + g++/clang + Boost + Zlib + optionally CUDA) |
| | PyTorch dependency is heavy (~2GB) |
| | But for an output-scoring evaluator, compilation is NOT needed |
| | The HPWL computation can be pure NumPy |

**Recommendation**: The evaluator must NOT require C++ compilation. Pure-Python scoring is essential.

---

## Summary of Audit

| Design Decision | Status | Action Required |
|----------------|--------|-----------------|
| "Clock-Aware" benchmark name | ⚠ Partially supported | Either rename to "FPGAPlacement" or design clock constraints from scratch |
| Clock is a hard validation gate (G4) | ❌ Unsupported | Drop G4 from initial design; add later if clock constraints are created |
| Score = -HPWL | ⚠ Partially supported | Acceptable; document that it differs from optimization proxy |
| Output-based scoring (Alternative C) | ✅ Verified | Proceed with pure-Python HPWL evaluator |
| .clk clock constraint files | ❌ Unsupported | Remove from initial design; requires greenfield effort |
| Site-type gate (G1) | ✅ Verified | Implement from existing code |
| Capacity gate (G2) | ✅ Verified | Implement from existing code |
| Carry-chain gate (G3) | ✅ Verified | Implement from existing code |
| ISPD 2016 benchmarks | ✅ Verified | Use FPGA01-FPGA12 |
| aug-elfPlace as baseline | ✅ Verified | Baseline confirmed |
| C++ compilation risk | ✅ Verified | Evaluator must be pure-Python |

## Revised Recommendation

**The benchmark should initially NOT be "clock-aware"** in the sense of clock region constraints, clock distribution, or clock skew optimization. The existing codebase does not support this framing.

Instead, the benchmark should be positioned as **FPGA Placement Optimization** — a wirelength-driven placement benchmark with legality constraints, using the ISPD 2016 benchmarks and aug-elfPlace as the baseline. This is what the existing codebase actually implements and can verify.

If "clock-aware" placement remains the goal, it must be designed as a **new contribution**:
1. Define clock region constraints (new file format + parser)
2. Define a clock quality metric (e.g., clock skew penalty)
3. Implement clock legality checking
4. Add clock-aware optimization to the evolvable code
