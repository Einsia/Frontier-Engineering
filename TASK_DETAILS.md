# Task Details

English | [简体中文](TASK_DETAILS_zh-CN.md)

Frontier-Eng currently ships tasks across the domains below. Each task is backed by a runnable evaluator and real engineering context. See each domain's folder under `benchmarks/` for per-task documentation and quickstart instructions.

We welcome new engineering problem ideas — even without complete verification code. Open an Issue describing the real-world background and engineering value, and we will rally the community around it.

<table>
  <thead>
    <tr>
      <th>Domain</th>
      <th>Task</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><b>Astrodynamics</b></td>
      <td><code>MannedLunarLanding</code></td>
      <td>Maximize CRTBP lunar payload under trajectory and dynamics constraints (Octave validated)</td>
    </tr>
    <tr>
      <td rowspan="2"><b>ParticlePhysics</b></td>
      <td><code>MuonTomography</code></td>
      <td>Muon detector placement optimization under flux, budget, and excavation constraints</td>
    </tr>
    <tr>
      <td><code>ProtonTherapyPlanning</code></td>
      <td>IMPT dose weight optimization under tumor coverage, OAR safety, and beam cost constraints</td>
    </tr>
    <tr>
      <td rowspan="3"><b>KernelEngineering</b></td>
      <td><code>MLA</code></td>
      <td>Multi-head latent attention decoding kernel (CUDA/Triton)</td>
    </tr>
    <tr>
      <td><code>TriMul</code></td>
      <td>Triangular multiplicative update kernel (CUDA/Triton)</td>
    </tr>
    <tr>
      <td><code>FlashAttention</code></td>
      <td>Causal scaled dot-product attention forward kernel optimized for GPU execution</td>
    </tr>
    <tr>
      <td rowspan="3"><b>SingleCellAnalysis</b></td>
      <td><code>denoising</code></td>
      <td>Open Problems single-cell RNA denoising</td>
    </tr>
    <tr>
      <td><code>perturbation_prediction</code></td>
      <td>Perturbation response prediction (NeurIPS 2023 scPerturb)</td>
    </tr>
    <tr>
      <td><code>predict_modality</code></td>
      <td>Cross-modality gene expression prediction (RNA → ADT), NeurIPS 2021</td>
    </tr>
    <tr>
      <td rowspan="3"><b>QuantumComputing</b></td>
      <td><code>routing_qftentangled</code></td>
      <td>QFT circuit routing optimization on IBM Falcon (gate count &amp; depth)</td>
    </tr>
    <tr>
      <td><code>clifford_t_synthesis</code></td>
      <td>Clifford+T synthesis optimization for QFT circuits</td>
    </tr>
    <tr>
      <td><code>cross_target_qaoa</code></td>
      <td>Cross-target robust QAOA optimization for IBM and IonQ backends</td>
    </tr>
    <tr>
      <td rowspan="3"><b>Cryptographic</b></td>
      <td><code>AES-128 CTR</code></td>
      <td>C++ AES-128 Counter mode throughput (OpenSSL verified)</td>
    </tr>
    <tr>
      <td><code>SHA-256</code></td>
      <td>C++ SHA-256 throughput (OpenSSL verified)</td>
    </tr>
    <tr>
      <td><code>SHA3-256</code></td>
      <td>C++ SHA3-256 throughput (OpenSSL verified)</td>
    </tr>
    <tr>
      <td rowspan="3"><b>CommunicationEngineering</b></td>
      <td><code>LDPCErrorFloor</code></td>
      <td>LDPC code error floor estimation via importance sampling on trapping sets</td>
    </tr>
    <tr>
      <td><code>PMDSimulation</code></td>
      <td>Polarization Mode Dispersion simulation with importance sampling for rare outage events</td>
    </tr>
    <tr>
      <td><code>RayleighFadingBER</code></td>
      <td>BER analysis under Rayleigh fading with importance sampling for deep fade events</td>
    </tr>
    <tr>
      <td rowspan="2"><b>EnergyStorage</b></td>
      <td><code>BatteryFastChargingProfile</code></td>
      <td>Fast-charge current-profile optimization under voltage, thermal, and degradation constraints</td>
    </tr>
    <tr>
      <td><code>BatteryFastChargingSPMe</code></td>
      <td>Staged fast-charge optimization under a high-fidelity SPMe-T-Aging electrochemical model</td>
    </tr>
    <tr>
      <td><b>SustainableDataCenterControl</b></td>
      <td><code>hand_written_control</code></td>
      <td>Joint control of load shifting, cooling, and battery dispatch in a data center</td>
    </tr>
    <tr>
      <td rowspan="4"><b>ReactionOptimisation</b></td>
      <td><code>snar_multiobjective</code></td>
      <td>Pareto-optimize continuous-flow SnAr reaction (yield vs. waste)</td>
    </tr>
    <tr>
      <td><code>mit_case1_mixed</code></td>
      <td>Mixed-variable reaction yield maximization (continuous settings + categorical catalyst)</td>
    </tr>
    <tr>
      <td><code>reizman_suzuki_pareto</code></td>
      <td>Pareto-optimize Suzuki coupling (yield vs. catalyst turnover)</td>
    </tr>
    <tr>
      <td><code>dtlz2_pareto</code></td>
      <td>DTLZ2 Pareto-front approximation</td>
    </tr>
    <tr>
      <td rowspan="3"><b>MolecularMechanics</b></td>
      <td><code>weighted_parameter_coverage</code></td>
      <td>Rare force-field parameter coverage under a molecule budget</td>
    </tr>
    <tr>
      <td><code>diverse_conformer_portfolio</code></td>
      <td>Low-energy, high-diversity conformer portfolio selection</td>
    </tr>
    <tr>
      <td><code>torsion_profile_fitting</code></td>
      <td>Force-field torsion-scale fitting against target energy profiles</td>
    </tr>
    <tr>
      <td rowspan="16"><b>Optics</b></td>
      <td><code>adaptive_constrained_dm_control</code></td>
      <td>Constrained deformable mirror (DM) control</td>
    </tr>
    <tr>
      <td><code>adaptive_temporal_smooth_control</code></td>
      <td>Temporal smoothness vs. correction quality trade-off in adaptive optics</td>
    </tr>
    <tr>
      <td><code>adaptive_energy_aware_control</code></td>
      <td>Energy-aware adaptive optics control</td>
    </tr>
    <tr>
      <td><code>adaptive_fault_tolerant_fusion</code></td>
      <td>Fault-tolerant multi-WFS slope fusion for adaptive optics control</td>
    </tr>
    <tr>
      <td><code>phase_weighted_multispot_single_plane</code></td>
      <td>Single-plane weighted multispot phase DOE</td>
    </tr>
    <tr>
      <td><code>phase_fourier_pattern_holography</code></td>
      <td>Fourier pattern holography</td>
    </tr>
    <tr>
      <td><code>phase_dammann_uniform_orders</code></td>
      <td>Dammann grating uniform diffraction orders</td>
    </tr>
    <tr>
      <td><code>phase_large_scale_weighted_spot_array</code></td>
      <td>Large-scale weighted spot array synthesis</td>
    </tr>
    <tr>
      <td><code>fiber_wdm_channel_power_allocation</code></td>
      <td>WDM channel and launch power allocation</td>
    </tr>
    <tr>
      <td><code>fiber_mcs_power_scheduling</code></td>
      <td>Joint MCS and power scheduling</td>
    </tr>
    <tr>
      <td><code>fiber_dsp_mode_scheduling</code></td>
      <td>Receiver DSP mode scheduling</td>
    </tr>
    <tr>
      <td><code>fiber_guardband_spectrum_packing</code></td>
      <td>Spectrum packing with guard-band constraints</td>
    </tr>
    <tr>
      <td><code>holographic_multifocus_power_ratio</code></td>
      <td>Multi-focus power ratio control</td>
    </tr>
    <tr>
      <td><code>holographic_multiplane_focusing</code></td>
      <td>Multi-plane holographic focusing</td>
    </tr>
    <tr>
      <td><code>holographic_multispectral_focusing</code></td>
      <td>Multispectral holographic focusing</td>
    </tr>
    <tr>
      <td><code>holographic_polarization_multiplexing</code></td>
      <td>Polarization-multiplexed holography</td>
    </tr>
    <tr>
      <td rowspan="2"><b>ComputerSystems</b></td>
      <td><code>MallocLab</code></td>
      <td>High-performance C memory allocator (utilization &amp; throughput)</td>
    </tr>
    <tr>
      <td><code>DuckDBWorkloadOptimization</code></td>
      <td>Index / materialized-view selection and query rewriting on official DuckDB workloads</td>
    </tr>
    <tr>
      <td><b>EngDesign</b></td>
      <td><code>CY_03, WJ_01, XY_05, AM_02, AM_03, YJ_02, YJ_03</code></td>
      <td>Multi-discipline tasks from <a href="https://github.com/AGI4Engineering/EngDesign">EngDesign</a>: drivers, denoising, CPU logic, path planning</td>
    </tr>
    <tr>
      <td rowspan="5"><b>InventoryOptimization</b></td>
      <td><code>tree_gsm_safety_stock</code></td>
      <td>Tree-structured multi-echelon safety-stock placement (GSM)</td>
    </tr>
    <tr>
      <td><code>general_meio</code></td>
      <td>General-topology MEIO with simulation-based objective</td>
    </tr>
    <tr>
      <td><code>joint_replenishment</code></td>
      <td>Multi-SKU joint replenishment with shared setup cost</td>
    </tr>
    <tr>
      <td><code>finite_horizon_dp</code></td>
      <td>Finite-horizon stochastic inventory control via time-varying policy</td>
    </tr>
    <tr>
      <td><code>disruption_eoqd</code></td>
      <td>EOQ lot-sizing optimization under supply disruptions</td>
    </tr>
    <tr>
      <td rowspan="3"><b>PyPortfolioOpt</b></td>
      <td><code>robust_mvo_rebalance</code></td>
      <td>Robust mean-variance rebalancing with sector / factor / turnover constraints</td>
    </tr>
    <tr>
      <td><code>cvar_stress_control</code></td>
      <td>CVaR stress-controlled portfolio allocation under return and exposure constraints</td>
    </tr>
    <tr>
      <td><code>discrete_rebalance_mip</code></td>
      <td>Discrete lot-constrained rebalancing with mixed-integer optimization</td>
    </tr>
    <tr>
      <td><b>MarketMaking</b></td>
      <td><code>InventoryAwareQuoting</code></td>
      <td>Inventory-aware DUAL quoting under adverse selection and position limits</td>
    </tr>
    <tr>
      <td rowspan="7"><b>JobShop</b></td>
      <td><code>abz</code></td>
      <td>JSSP ABZ family (Adams, Balas, Zawack 1988)</td>
    </tr>
    <tr>
      <td><code>ft</code></td>
      <td>JSSP FT family (Fisher and Thompson 1963)</td>
    </tr>
    <tr>
      <td><code>la</code></td>
      <td>JSSP LA family (Lawrence 1984)</td>
    </tr>
    <tr>
      <td><code>orb</code></td>
      <td>JSSP ORB family (Applegate and Cook 1991)</td>
    </tr>
    <tr>
      <td><code>swv</code></td>
      <td>JSSP SWV family (Storer, Wu, Vaccari 1992)</td>
    </tr>
    <tr>
      <td><code>ta</code></td>
      <td>JSSP Taillard family (1993)</td>
    </tr>
    <tr>
      <td><code>yn</code></td>
      <td>JSSP YN family (Yamada and Nakano 1992)</td>
    </tr>
    <tr>
      <td rowspan="4"><b>StructuralOptimization</b></td>
      <td><code>ISCSO2015</code></td>
      <td>Minimize weight of 45-bar 2D truss under stress / displacement constraints</td>
    </tr>
    <tr>
      <td><code>ISCSO2023</code></td>
      <td>Minimize weight of 284-member 3D tower with discrete sections</td>
    </tr>
    <tr>
      <td><code>TopologyOptimization</code></td>
      <td>MBB beam 2D topology optimization (SIMP), volume-constrained compliance minimization</td>
    </tr>
    <tr>
      <td><code>PyMOTOSIMPCompliance</code></td>
      <td>pyMOTO-based 2D beam topology optimization (SIMP + OC/MMA) under a volume-fraction constraint</td>
    </tr>
    <tr>
      <td rowspan="6"><b>Robotics</b></td>
      <td><code>DynamicObstacleAvoidanceNavigation</code></td>
      <td>Navigate a differential-drive robot from start to goal in a dynamic environment</td>
    </tr>
    <tr>
      <td><code>QuadrupedGaitOptimization</code></td>
      <td>Maximize forward locomotion speed of a quadruped (MuJoCo) by optimizing 8 gait parameters</td>
    </tr>
    <tr>
      <td><code>RobotArmCycleTimeOptimization</code></td>
      <td>Minimize motion time of a 7-DOF KUKA LBR iiwa arm (PyBullet), collision-free</td>
    </tr>
    <tr>
      <td><code>PIDTuning</code></td>
      <td>Tune cascaded PID gains for a 2D quadrotor across multiple flight scenarios</td>
    </tr>
    <tr>
      <td><code>UAVInspectionCoverageWithWind</code></td>
      <td>UAV inspection coverage under wind field disturbance</td>
    </tr>
    <tr>
      <td><code>CoFlyersVasarhelyiTuning</code></td>
      <td>Tune the Vasarhelyi flocking parameters for the CoFlyers swarm system</td>
    </tr>
    <tr>
      <td rowspan="2"><b>Aerodynamics</b></td>
      <td><code>CarAerodynamicsSensing</code></td>
      <td>30 sensor locations on 3D car surface for pressure field reconstruction</td>
    </tr>
    <tr>
      <td><code>DawnAircraftDesignOptimization</code></td>
      <td>Jointly optimize wing, fuselage, and propulsion variables to minimize total aircraft mass</td>
    </tr>
    <tr>
      <td><b>WirelessChannelSimulation</b></td>
      <td><code>HighReliableSimulation</code></td>
      <td>Importance-sampling BER estimator for Hamming(127,120)</td>
    </tr>
    <tr>
      <td><b>PowerSystems</b></td>
      <td><code>EV2GymSmartCharging</code></td>
      <td>Upstream-aligned EV smart charging scheduling</td>
    </tr>
    <tr>
      <td rowspan="2"><b>ContinuousCasting</b></td>
      <td><code>CuttingOptimization</code></td>
      <td>Cut a continuously cast billet into pieces to minimize scrapped length and match a customer target (offline; the optimum is reachable)</td>
    </tr>
    <tr>
      <td><code>CuttingOptimizationOnline</code></td>
      <td>Online (closed-loop) cutting where 0.8 m scrap segments are revealed only within a reveal horizon — info asymmetry empirically keeps agents below the clairvoyant optimum (observed, not a proven lower bound)</td>
    </tr>
    <tr>
      <td><b>AdditiveManufacturing</b></td>
      <td><code>DiffSimThermalControl</code></td>
      <td>Process optimization in additive manufacturing via differentiable simulation</td>
    </tr>
  </tbody>
</table>
