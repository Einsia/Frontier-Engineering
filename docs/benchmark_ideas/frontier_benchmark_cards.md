# Frontier Benchmark Cards

Generated on 2026-03-12.
Drafted with the `frontier-benchmark-contributor` skill.

Selection policy:

1. Prefer authentic and traceable data sources or canonical benchmark instances.
2. Prefer offline reproducibility and stable evaluation.
3. Prefer `task=unified` where practical.
4. Downgrade or defer items with weak provenance, unclear redistribution terms, or heavyweight runtime stacks.

## P1 Priority

### 1. EOQ+MOQ Annual Cost Minimization
- Domain: Inventory optimization
- Upstream: Stockpyl EOQ
- Canonical source: Stockpyl official EOQ docs and Snyder/Shen textbook formulas; no external dataset
- License / redistribution: Stockpyl MIT; no data redistribution issue
- Baseline: `economic_order_quantity` plus outer feasible-set enumeration for MOQ
- Agent interface: `solve(params) -> Q`
- Metrics: `annual_total_cost`, `valid`
- Recommended integration: `unified`
- Main risk: MOQ is an outer constraint rather than a native closed-form Stockpyl solver

### 2. EOQ All-Units Discount Optimization
- Domain: Inventory optimization
- Upstream: Stockpyl EOQ with all-units discounts
- Canonical source: Stockpyl official EOQ docs; no external dataset
- License / redistribution: Stockpyl MIT; no data redistribution issue
- Baseline: `economic_order_quantity_with_all_units_discounts`
- Agent interface: `solve(params) -> Q`
- Metrics: `annual_total_cost`, `chosen_region`, `valid`
- Recommended integration: `unified`
- Main risk: Feasible regions become subtle when all-units discounts are combined with MOQ

### 3. EOQ Incremental Discount Optimization
- Domain: Inventory optimization
- Upstream: Stockpyl EOQ with incremental discounts
- Canonical source: Stockpyl official EOQ docs; no external dataset
- License / redistribution: Stockpyl MIT; no data redistribution issue
- Baseline: `economic_order_quantity_with_incremental_discounts`
- Agent interface: `solve(params) -> Q`
- Metrics: `annual_total_cost`, `chosen_region`, `valid`
- Recommended integration: `unified`
- Main risk: Incremental discount cost accounting is easy to implement incorrectly

### 4. Poisson-Demand (r,Q) Exact Optimization
- Domain: Inventory optimization
- Upstream: Stockpyl `rq`
- Canonical source: Stockpyl single-echelon inventory tutorial and `r_q_poisson_exact`
- License / redistribution: Stockpyl MIT; no data redistribution issue
- Baseline: `r_q_poisson_exact`
- Agent interface: `solve(params) -> (r, Q)`
- Metrics: `cost`, `valid`
- Recommended integration: `unified`
- Main risk: Service-level constraints may need an outer audit rather than a native function argument

### 5. Normal-Demand (r,Q) with 95% Service-Level Constraint
- Domain: Inventory optimization
- Upstream: Stockpyl `rq` normal-demand approximations
- Canonical source: Stockpyl official `rq` docs and tutorial
- License / redistribution: Stockpyl MIT; no data redistribution issue
- Baseline: `r_q_eil_approximation`, `r_q_eoqss_approximation`, or `r_q_loss_function_approximation`
- Agent interface: `solve(params) -> (r, Q)`
- Metrics: `cost`, `service_level_feasible`, `valid`
- Recommended integration: `unified`
- Main risk: Approximation quality can drift around the service-level boundary

### 6. FT10 Dispatching Rule Optimization
- Domain: Job shop scheduling
- Upstream: JobShopLib / Fisher-Thompson FT10
- Canonical source: JobShopLib bundled `ft10`; original instance from Fisher and Thompson (1963)
- License / redistribution: JobShopLib MIT; original instance should preferably be loaded from the library or re-encoded carefully
- Baseline: CP-SAT or built-in dispatching rules
- Agent interface: `solve(instance) -> schedule`
- Metrics: `makespan`, `valid`
- Recommended integration: `unified`
- Main risk: Original instance licensing is less explicit than the code license

### 7. LA16 Dispatching Rule Optimization
- Domain: Job shop scheduling
- Upstream: JobShopLib / Lawrence LA16
- Canonical source: JobShopLib bundled `la16`; original instance from Lawrence (1984)
- License / redistribution: JobShopLib MIT; original instance should preferably be loaded from the library or re-encoded carefully
- Baseline: CP-SAT or built-in dispatching rules
- Agent interface: `solve(instance) -> schedule`
- Metrics: `makespan`, `valid`
- Recommended integration: `unified`
- Main risk: Same provenance caveat as FT10

### 8. FT10 Neighborhood Move Selection
- Domain: Job shop scheduling
- Upstream: JobShopLib plus SA/CP-SAT
- Canonical source: Canonical FT10 benchmark instance
- License / redistribution: JobShopLib MIT; instance provenance should be tied to JobShopLib or another canonical loader
- Baseline: Simulated annealing default neighborhood or CP-SAT optimal reference 930
- Agent interface: `choose_moves(state) -> move`
- Metrics: `makespan`, `improvement_over_baseline`, `valid`
- Recommended integration: `unified`
- Main risk: The agent surface must stay narrow so the solver itself is not editable

### 9. LA16 Neighborhood Move Selection
- Domain: Job shop scheduling
- Upstream: JobShopLib plus SA/CP-SAT
- Canonical source: Canonical LA16 benchmark instance
- License / redistribution: JobShopLib MIT; instance provenance should be tied to JobShopLib or another canonical loader
- Baseline: Simulated annealing default neighborhood or CP-SAT reference 945
- Agent interface: `choose_moves(state) -> move`
- Metrics: `makespan`, `improvement_over_baseline`, `valid`
- Recommended integration: `unified`
- Main risk: Reproducibility depends on fixed random seeds and a pinned neighborhood set

### 10. DuckDB TPC-H Materialization / Index Selection
- Domain: Database optimization
- Upstream: DuckDB plus official TPC-H extension
- Canonical source: DuckDB official `tpch` extension with local `CALL dbgen(sf=...)`
- License / redistribution: DuckDB MIT; TPC-H data generated locally to avoid redistributing raw benchmark tables
- Baseline: No additional materialization or a simple rule-based config
- Agent interface: `solve(workload) -> config`
- Metrics: `total_runtime`, `correctness`, `valid`
- Recommended integration: `unified`
- Main risk: Native DuckDB indexes may have limited impact, so the benchmark may work better around materialization or layout

### 11. DuckDB TPC-H Query Rewriting
- Domain: Database optimization
- Upstream: DuckDB plus official TPC-H queries
- Canonical source: DuckDB official TPC-H query set and local generated data
- License / redistribution: DuckDB MIT; data generated locally
- Baseline: Original SQL
- Agent interface: `rewrite(sql) -> sql`
- Metrics: `runtime_ratio`, `result_match`, `valid`
- Recommended integration: `unified`
- Main risk: Semantic equivalence checks must be strict and deterministic

### 12. DuckDB TPC-H Pre-Aggregation Selection
- Domain: Database optimization
- Upstream: DuckDB plus TPC-H
- Canonical source: DuckDB official TPC-H extension with local generated data
- License / redistribution: DuckDB MIT; data generated locally
- Baseline: No pre-aggregation
- Agent interface: `solve(workload) -> ddl_plan`
- Metrics: `total_runtime`, `storage_overhead`, `valid`
- Recommended integration: `unified`
- Main risk: The task can drift into schema design rather than benchmark-guided optimization if not scoped tightly

### 13. 2D Grid Obstacle-Avoiding Path Planning
- Domain: Motion planning
- Upstream: `caelan/motion-planners`
- Canonical source: Official repo plus fixed-seed synthetic grid maps
- License / redistribution: MIT; synthetic maps have no redistribution issue
- Baseline: A* or RRT
- Agent interface: `plan_path(map, start, goal) -> path`
- Metrics: `path_length`, `success_rate`, `runtime`
- Recommended integration: `unified`
- Main risk: Map authenticity is weaker than a canonical real-world benchmark

### 14. 2D Narrow-Passage Planning
- Domain: Motion planning
- Upstream: `caelan/motion-planners`
- Canonical source: Official repo plus fixed-seed synthetic narrow-passage maps
- License / redistribution: MIT; synthetic maps have no redistribution issue
- Baseline: BiRRT or RRT*
- Agent interface: `plan_path(map, start, goal) -> path`
- Metrics: `success_rate`, `path_cost`, `runtime`
- Recommended integration: `unified`
- Main risk: The benchmark is synthetic rather than tied to a public robotics map dataset

### 15. Multi-Robot Prioritized Planning
- Domain: Motion planning
- Upstream: `caelan/motion-planners`
- Canonical source: Official repo plus fixed-seed multi-agent grid instances
- License / redistribution: MIT; synthetic instances have no redistribution issue
- Baseline: Prioritized planning or independent A*
- Agent interface: `solve(map, agents) -> paths`
- Metrics: `total_path_length`, `collisions`, `runtime`
- Recommended integration: `unified`
- Main risk: Collision checking and tie-breaking must remain deterministic

## P2 Priority

### 16. Cantilever Compliance Topology Optimization
- Domain: Structural optimization
- Upstream: pyMOTO
- Canonical source: pyMOTO official examples and standard FEM setup
- License / redistribution: MIT; example data can be redistributed with the repo
- Baseline: Official SIMP plus OC/MMA
- Agent interface: `solve(load_case) -> density`
- Metrics: `compliance`, `volume_fraction`, `valid`
- Recommended integration: `unified`
- Main risk: Mesh size must be kept small for fast evaluation

### 17. MBB Beam Topology Optimization
- Domain: Structural optimization
- Upstream: pyMOTO
- Canonical source: pyMOTO official examples
- License / redistribution: MIT
- Baseline: Official SIMP plus OC/MMA
- Agent interface: `solve(load_case) -> density`
- Metrics: `compliance`, `volume_fraction`, `valid`
- Recommended integration: `unified`
- Main risk: Filter and projection choices can dominate the result

### 18. Bridge Topology Optimization
- Domain: Structural optimization
- Upstream: pyMOTO
- Canonical source: pyMOTO official examples or standard textbook bridge setup
- License / redistribution: MIT
- Baseline: Official SIMP plus OC/MMA
- Agent interface: `solve(load_case) -> density`
- Metrics: `compliance`, `volume_fraction`, `checkerboard_penalty`
- Recommended integration: `unified`
- Main risk: The canonical geometry must be frozen in the task spec

### 19. Fuel-Minimizing Ship Weather Routing
- Domain: Maritime optimization
- Upstream: 52North WeatherRoutingTool
- Canonical source: Official WeatherRoutingTool algorithms and, if available, official demo weather fields; otherwise clearly labeled synthetic grids
- License / redistribution: MIT; synthetic weather grids avoid redistribution issues
- Baseline: Default shortest-route or official routing heuristic
- Agent interface: `solve(instance) -> waypoints`
- Metrics: `fuel_cost`, `travel_time`, `constraint_violations`
- Recommended integration: `unified`
- Main risk: If official demo weather fields are not usable, the benchmark becomes synthetic

### 20. Dynamic-Current Minimum-Time Routing
- Domain: Maritime optimization
- Upstream: HALEM
- Canonical source: HALEM official repo and test/example current fields, or clearly labeled synthetic current field
- License / redistribution: MIT
- Baseline: `HALEM_time`
- Agent interface: `solve(instance) -> route`
- Metrics: `travel_time`, `valid`
- Recommended integration: `unified`
- Main risk: Need to confirm that official example fields are light enough to vendor or reproduce

### 21. Depth-Constrained Cost-Minimizing Routing
- Domain: Maritime optimization
- Upstream: HALEM
- Canonical source: HALEM official repo and example current/depth fields
- License / redistribution: MIT
- Baseline: `HALEM_cost` or `HALEM_co2`
- Agent interface: `solve(instance) -> route`
- Metrics: `route_cost`, `grounding_violations`, `valid`
- Recommended integration: `unified`
- Main risk: Any transformation into local arrays must be documented carefully

### 22. Intraday Operation with Storage
- Domain: Power systems
- Upstream: PyPSA
- Canonical source: PyPSA official example networks
- License / redistribution: MIT; official example networks are preferred
- Baseline: PyPSA default linear optimization
- Agent interface: `solve(network) -> dispatch`
- Metrics: `opex`, `curtailment`, `valid`
- Recommended integration: `unified`
- Main risk: Linopy/HiGHS runtime stack is heavier than pure Python tasks

### 23. Transmission Expansion Planning
- Domain: Power systems
- Upstream: PyPSA
- Canonical source: PyPSA official example networks
- License / redistribution: MIT
- Baseline: PyPSA default capacity expansion model
- Agent interface: `solve(network) -> expansion_plan`
- Metrics: `total_system_cost`, `unmet_demand`, `valid`
- Recommended integration: `unified`
- Main risk: Time horizon must be reduced to keep runtime bounded

### 24. Renewable Siting plus Line Expansion
- Domain: Power systems
- Upstream: PyPSA
- Canonical source: PyPSA official example networks or a clearly documented toy network derived from them
- License / redistribution: MIT
- Baseline: PyPSA default optimization
- Agent interface: `solve(network) -> plan`
- Metrics: `capex_opex_total`, `renewable_share`, `valid`
- Recommended integration: `unified`
- Main risk: A derived toy case requires explicit provenance and transformation notes

### 25. Single-Day Multi-Energy Scheduling
- Domain: Integrated energy systems
- Upstream: MESMO
- Canonical source: MESMO official example cases and official repo data
- License / redistribution: MIT; official examples preferred
- Baseline: MESMO or CVXPY default model
- Agent interface: `solve(instance) -> schedule`
- Metrics: `total_cost`, `feasibility`, `valid`
- Recommended integration: `unified`
- Main risk: CVXPY and solver dependencies are relatively heavy

### 26. Joint Investment plus Operations for Heat Pump and Storage
- Domain: Integrated energy systems
- Upstream: MESMO
- Canonical source: MESMO official example case or a clearly documented reduced derivative
- License / redistribution: MIT
- Baseline: MESMO default optimization
- Agent interface: `solve(instance) -> design_and_ops`
- Metrics: `lifecycle_cost`, `capacity_feasible`, `valid`
- Recommended integration: `unified`
- Main risk: Investment variables increase runtime significantly

### 27. SnAr Reaction Condition Optimization
- Domain: Chemical process optimization
- Upstream: Summit
- Canonical source: Summit official `SnarBenchmark` and associated benchmark paper
- License / redistribution: Summit MIT; benchmark is a simulator, so no external data redistribution issue
- Baseline: SOBO or Nelder-Mead
- Agent interface: `solve(experiment) -> conditions`
- Metrics: `best_objective`, `budget_efficiency`, `valid`
- Recommended integration: `unified`
- Main risk: Budget and random seed must be fixed tightly

### 28. SnAr Multi-Objective Optimization
- Domain: Chemical process optimization
- Upstream: Summit
- Canonical source: Summit official benchmark suite
- License / redistribution: MIT
- Baseline: Scalarized official strategy such as SOBO
- Agent interface: `solve(experiment) -> trial_sequence`
- Metrics: `best_scalarized_score` or `pareto_hypervolume`, `valid`
- Recommended integration: `unified`
- Main risk: Multi-objective scoring must be frozen before implementation

### 29. EV Price-Arbitrage Charging
- Domain: EV charging optimization
- Upstream: EV2Gym
- Canonical source: EV2Gym official example configs and open-source data references
- License / redistribution: MIT; chosen config and any bundled data must be checked case by case
- Baseline: `ChargeAsFastAsPossible` or official MPC/oracle heuristic
- Agent interface: `solve(env) -> actions`
- Metrics: `energy_cost`, `user_satisfaction`, `valid`
- Recommended integration: `unified`
- Main risk: Need to confirm the specific config data can be redistributed or reconstructed locally

### 30. EV Scheduling with Overload and Voltage Constraints
- Domain: EV charging optimization
- Upstream: EV2Gym
- Canonical source: EV2Gym official configs
- License / redistribution: MIT; config provenance must be pinned
- Baseline: Official MPC or heuristic
- Agent interface: `solve(env) -> actions`
- Metrics: `cost`, `overload_penalty`, `voltage_penalty`
- Recommended integration: `unified`
- Main risk: The grid proxy must be made stable enough for repeated evaluation

### 31. Small Reservoir Network Cost Minimization
- Domain: Water resources optimization
- Upstream: CALVIN
- Canonical source: CALVIN official site, official GitHub, and official example data lineage
- License / redistribution: CALVIN code MIT; full data redistribution needs separate confirmation
- Baseline: Pyomo MILP
- Agent interface: `solve(instance) -> policy`
- Metrics: `total_cost`, `shortage_penalty`, `valid`
- Recommended integration: `unified`
- Main risk: Official data is large and externally hosted, so a smaller benchmark likely needs a carefully documented derivative

### 32. Drought-Scenario Water Allocation
- Domain: Water resources optimization
- Upstream: CALVIN
- Canonical source: CALVIN official model and published problem framing; likely a reduced synthetic or derived network
- License / redistribution: CALVIN code MIT; derived data must be labeled clearly
- Baseline: Pyomo MILP
- Agent interface: `solve(instance) -> allocation`
- Metrics: `total_cost`, `shortage`, `reservoir_violations`
- Recommended integration: `unified`
- Main risk: It must not be misrepresented as official CALVIN data if the network is reduced or synthetic

### 33. Markowitz Minimum Variance with Return Floor
- Domain: Portfolio optimization
- Upstream: PyPortfolioOpt
- Canonical source: PyPortfolioOpt repo test returns or another fixed local returns matrix; upstream market-data provenance is relatively weak
- License / redistribution: Code MIT; market data licensing requires extra verification
- Baseline: `EfficientFrontier`
- Agent interface: `solve(returns) -> weights`
- Metrics: `annual_return`, `volatility`, `sharpe`, `max_drawdown`
- Recommended integration: `unified`
- Main risk: Data authenticity is weaker than canonical academic benchmarks unless a stronger source is chosen

### 34. Maximum Sharpe Static Portfolio
- Domain: Portfolio optimization
- Upstream: PyPortfolioOpt
- Canonical source: Same as above; stronger if replaced by a licensed market snapshot or clearly labeled synthetic returns
- License / redistribution: Code MIT; any real market data requires separate license review
- Baseline: `max_sharpe()`
- Agent interface: `solve(returns) -> weights`
- Metrics: `sharpe`, `turnover_vs_baseline`, `valid`
- Recommended integration: `unified`
- Main risk: Weak data provenance if using ad hoc historical prices

### 35. Rebalancing with Transaction Cost and Leverage Limits
- Domain: Portfolio optimization
- Upstream: PyPortfolioOpt
- Canonical source: Fixed returns matrix from official tests or synthetic data unless a licensed market dataset is selected
- License / redistribution: Code MIT; real price data needs explicit license verification
- Baseline: `EfficientFrontier` plus transaction-cost objective
- Agent interface: `solve(returns, w0) -> weights`
- Metrics: `net_sharpe`, `turnover`, `max_leverage_violation`
- Recommended integration: `unified`
- Main risk: This task is highly exposed to data provenance weakness

### 36. Small Fab Dispatch Rule Composition
- Domain: Manufacturing scheduling
- Upstream: SimRLFab
- Canonical source: SimRLFab official default semiconductor config and related paper
- License / redistribution: MIT; bundled configs appear open
- Baseline: FIFO, SPT, or LPT
- Agent interface: `schedule_fab(state) -> priority`
- Metrics: `throughput`, `avg_flow_time`, `valid`
- Recommended integration: `bespoke wrapper`
- Main risk: The simulator stack is heavier than typical single-file tasks

### 37. Urgent-Order Multi-Objective Dispatching
- Domain: Manufacturing scheduling
- Upstream: SimRLFab
- Canonical source: Official SimRLFab config plus explicit local reward shaping
- License / redistribution: MIT
- Baseline: FIFO, SPT, or LPT
- Agent interface: `schedule_fab(state) -> priority`
- Metrics: `weighted_flow_time_wip_tardiness`, `valid`
- Recommended integration: `bespoke wrapper`
- Main risk: Reward design can easily make the benchmark unstable

### 38. 3D Urban Drone Obstacle-Avoiding Path Planning
- Domain: Drone path planning
- Upstream: `martin0004/drone_path_planning`
- Canonical source: Official repo plus San Francisco `colliders.csv` lineage from the Udacity FCND project
- License / redistribution: Repo contains `LICENSE.txt`; map-data lineage should be documented explicitly
- Baseline: Repo RRT implementation
- Agent interface: `plan_3d_path(terrain, start, goal) -> path`
- Metrics: `path_length`, `collisions`, `runtime`
- Recommended integration: `unified`
- Main risk: Provenance is a lineage chain rather than a formal canonical benchmark

### 39. Energy-Penalized 3D Path Planning
- Domain: Drone path planning
- Upstream: `martin0004/drone_path_planning`
- Canonical source: Same lineage as above or a clearly labeled synthetic terrain
- License / redistribution: Same caveat as above
- Baseline: 3D A* or RRT
- Agent interface: `plan_3d_path(terrain, start, goal) -> path`
- Metrics: `path_length_plus_height_penalty`, `valid`
- Recommended integration: `unified`
- Main risk: If changed to synthetic terrain, the benchmark authenticity drops further

### 40. UAV Formation Convergence Control
- Domain: Multi-agent control
- Upstream: CoFlyers
- Canonical source: CoFlyers official Vasarhelyi example and repo configs
- License / redistribution: GPL-3.0; MATLAB/Simulink dependencies are significant
- Baseline: Official Vasarhelyi algorithm
- Agent interface: `solve(state) -> desired_velocities`
- Metrics: `convergence_time`, `collisions`, `control_energy`
- Recommended integration: `bespoke wrapper`
- Main risk: GPL and MATLAB dependencies make integration expensive

## P3 Priority

### 41. HALE Aircraft Design Optimization
- Domain: Aerospace design
- Upstream: DawnDesignTool
- Canonical source: Official repo `design_opt.py` and related paper; assumptions come from the model rather than a public benchmark dataset
- License / redistribution: MIT
- Baseline: Official `design_opt.py` flow
- Agent interface: `solve_design(spec) -> design`
- Metrics: `weight` or `cruise_power`, `constraint_feasible`
- Recommended integration: `unified`
- Main risk: Official model provenance is fine, but not the same as a canonical public benchmark instance

### 42. Small Imaging-System Optical Optimization
- Domain: Optical design
- Upstream: Optiland
- Canonical source: Optiland official examples; avoid hidden dependency on external materials databases
- License / redistribution: MIT; any external glass/material database needs separate terms review
- Baseline: Official optimizer and merit function
- Agent interface: `solve(system) -> lens_params`
- Metrics: `mtf_loss`, `aberration_score`, `valid`
- Recommended integration: `unified`
- Main risk: Material-database provenance can become muddy quickly

### 43. Small-Molecule Force-Field Parameter Fitting
- Domain: Molecular simulation
- Upstream: OpenFF Toolkit / BespokeFit
- Canonical source: OpenFF official examples and BespokeFit paper; actual QM reference set still needs a canonical selection
- License / redistribution: MIT
- Baseline: OpenFF recommended parameterization flow
- Agent interface: `fit_ff_params(dataset) -> params`
- Metrics: `energy_rmse`, `force_rmse`, `valid`
- Recommended integration: `bespoke wrapper`
- Main risk: The hard provenance question lies in the QM reference set, not the toolkit code

### 44. MD Parameter Performance Tuning
- Domain: Molecular simulation
- Upstream: OpenFF Toolkit plus OpenMM ecosystem
- Canonical source: OpenFF official example molecules; not a canonical performance benchmark
- License / redistribution: OpenFF MIT; additional dependency terms vary
- Baseline: Default integrator and cutoff settings
- Agent interface: `tune_md(system) -> md_config`
- Metrics: `throughput`, `energy_stability`, `valid`
- Recommended integration: `bespoke wrapper`
- Main risk: Results are highly hardware- and version-sensitive

### 45. Multiple Sequence Alignment Quality-Time Tradeoff
- Domain: Bioinformatics
- Upstream: Sequoya
- Canonical source: Sequoya official repo and paper; a serious benchmark should instead pin a canonical subset such as BAliBASE
- License / redistribution: Code MIT; benchmark-dataset terms must be checked separately
- Baseline: Sequoya default parameters
- Agent interface: `align(seqs) -> alignment`
- Metrics: `alignment_score`, `runtime`, `valid`
- Recommended integration: `bespoke wrapper`
- Main risk: Benchmark value depends more on dataset provenance than on the code package

### 46. Gap-Penalty-Sensitive MSA Optimization
- Domain: Bioinformatics
- Upstream: Sequoya
- Canonical source: Same as above; should wait for a verified benchmark dataset choice
- License / redistribution: Code MIT; dataset terms unresolved
- Baseline: Default NSGA-II or M2Align-style configuration
- Agent interface: `align(seqs) -> alignment`
- Metrics: `sp_score`, `tc_score`, `gap_score`, `runtime`
- Recommended integration: `bespoke wrapper`
- Main risk: Dataset provenance and scoring setup would dominate the implementation effort

### 47. Additive-Manufacturing Differentiable Simulation Optimization
- Domain: Manufacturing simulation
- Upstream: `differentiable-simulation-am`
- Canonical source: Official repo notebooks and bundled `data/`
- License / redistribution: MIT
- Baseline: Default gradient-descent setup from the paper and repo
- Agent interface: `solve(params0) -> params`
- Metrics: `best_loss`, `sim_calls`, `valid`
- Recommended integration: `unified`
- Main risk: The repo is notebook-heavy and needs stabilization into a clean evaluator

### 48. Offline Driving Path and Behavior Planning
- Domain: Autonomous driving
- Upstream: CARLA
- Canonical source: CARLA official simulator and official maps/assets exported offline
- License / redistribution: Code MIT, assets CC-BY, Unreal-related terms add complexity
- Baseline: IDM plus rule-based lane changes
- Agent interface: `solve(state) -> controls`
- Metrics: `collisions`, `avg_speed`, `brake_events`, `fuel_proxy`
- Recommended integration: `bespoke wrapper`
- Main risk: Asset and engine licensing complexity makes this a poor first-batch candidate

### 49. Data-Center Scheduling plus Cooling Control
- Domain: Data-center optimization
- Upstream: Hewlett Packard `dc-rl`
- Canonical source: Official repo environments and examples
- License / redistribution: Mixed MIT and CC BY-NC 4.0 terms
- Baseline: Fixed MARL or heuristic policy
- Agent interface: `solve(state) -> actions`
- Metrics: `energy`, `peak_power`, `temp_violations`
- Recommended integration: `bespoke wrapper`
- Main risk: Mixed licensing and a heavy environment stack

### 50. Optical-System Lightweighting
- Domain: Optical design
- Upstream: Optiland
- Canonical source: Optiland official examples; any external glass/material database must be cited separately
- License / redistribution: MIT for code; external material-data terms may differ
- Baseline: Official optimizer with thickness and quality constraints
- Agent interface: `solve(system) -> lens_params`
- Metrics: `total_thickness`, `image_quality`, `valid`
- Recommended integration: `unified`
- Main risk: The code is relatively clean, but materials provenance still needs careful documentation

## Source Index

- Stockpyl GitHub: https://github.com/LarrySnyder/stockpyl
- Stockpyl EOQ docs: https://stockpyl.readthedocs.io/en/latest/api/seio/eoq.html
- Stockpyl RQ docs: https://stockpyl.readthedocs.io/en/latest/api/seio/rq.html
- Stockpyl single-echelon tutorial: https://stockpyl.readthedocs.io/en/latest/tutorial/tutorial_seio.html
- JobShopLib: https://github.com/Pabloo22/job_shop_lib
- Job Shop Scheduling Benchmark Environments: https://github.com/ai-for-decision-making-tue/Job_Shop_Scheduling_Benchmark_Environments_and_Instances
- DuckDB TPC-H extension: https://duckdb.org/docs/stable/core_extensions/tpch
- DuckDB benchmark docs: https://duckdb.org/docs/1.3/guides/performance/benchmarks.html
- motion-planners: https://github.com/caelan/motion-planners
- pyMOTO: https://github.com/aatmdelissen/pyMOTO
- WeatherRoutingTool: https://github.com/52North/WeatherRoutingTool
- HALEM: https://github.com/TUDelft-CITG/halem
- PyPSA: https://github.com/PyPSA/PyPSA
- MESMO: https://github.com/mesmo-dev/mesmo
- Summit: https://github.com/sustainable-processes/summit
- EV2Gym: https://github.com/StavrosOrf/EV2Gym
- CALVIN official site: https://calvin.ucdavis.edu/
- CALVIN GitHub: https://github.com/ucd-cws/calvin
- PyPortfolioOpt: https://github.com/PyPortfolio/PyPortfolioOpt
- SimRLFab: https://github.com/AndreasKuhnle/SimRLFab
- drone_path_planning: https://github.com/martin0004/drone_path_planning
- CoFlyers: https://github.com/micros-uav/CoFlyers
- DawnDesignTool: https://github.com/peterdsharpe/DawnDesignTool
- Optiland: https://github.com/HarrisonKramer/optiland
- OpenFF Toolkit: https://github.com/openforcefield/openff-toolkit
- OpenFF BespokeFit: https://github.com/openforcefield/openff-bespokefit
- Sequoya GitHub: https://github.com/benhid/Sequoya
- Sequoya paper: https://academic.oup.com/bioinformatics/article-abstract/36/12/3892/5823295
- differentiable-simulation-am: https://github.com/mojtabamozaffar/differentiable-simulation-am
- CARLA: https://github.com/carla-simulator/carla
- dc-rl: https://github.com/HewlettPackard/dc-rl
