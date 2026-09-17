# 任务详情

[English](TASK_DETAILS.md) | 简体中文

Frontier-Eng 目前已覆盖以下领域的任务。每个任务均配有可运行的 evaluator 与真实工程背景。详细文档和快速上手说明见各领域 `benchmarks/` 子目录。

欢迎提出新的工程问题——即使暂时没有完整的 verifier 代码也没关系。提交 Issue 描述现实背景与工程价值，我们会将其纳入规划并集结社区共同攻克。

<table>
  <thead>
    <tr>
      <th>领域</th>
      <th>任务</th>
      <th>描述</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><b>Astrodynamics</b></td>
      <td><code>MannedLunarLanding</code></td>
      <td>在 CRTBP 轨道约束下最大化月球着陆载荷（Octave 验证）</td>
    </tr>
    <tr>
      <td rowspan="2"><b>ParticlePhysics</b></td>
      <td><code>MuonTomography</code></td>
      <td>在缪子通量、预算与开挖约束下优化探测器布局</td>
    </tr>
    <tr>
      <td><code>ProtonTherapyPlanning</code></td>
      <td>在肿瘤覆盖、危及器官保护与束流成本约束下优化 IMPT 剂量权重</td>
    </tr>
    <tr>
      <td rowspan="3"><b>KernelEngineering</b></td>
      <td><code>MLA</code></td>
      <td>多头潜在注意力（MLA）解码内核（CUDA/Triton）</td>
    </tr>
    <tr>
      <td><code>TriMul</code></td>
      <td>三角乘法更新内核（CUDA/Triton）</td>
    </tr>
    <tr>
      <td><code>FlashAttention</code></td>
      <td>为 GPU 执行优化因果型 scaled dot-product attention 前向内核</td>
    </tr>
    <tr>
      <td rowspan="3"><b>SingleCellAnalysis</b></td>
      <td><code>denoising</code></td>
      <td>Open Problems 单细胞 RNA 去噪</td>
    </tr>
    <tr>
      <td><code>perturbation_prediction</code></td>
      <td>扰动响应预测（NeurIPS 2023 scPerturb）</td>
    </tr>
    <tr>
      <td><code>predict_modality</code></td>
      <td>跨模态基因表达预测（RNA → ADT），NeurIPS 2021</td>
    </tr>
    <tr>
      <td rowspan="3"><b>QuantumComputing</b></td>
      <td><code>routing_qftentangled</code></td>
      <td>QFT 线路路由优化，IBM Falcon（gate count &amp; depth）</td>
    </tr>
    <tr>
      <td><code>clifford_t_synthesis</code></td>
      <td>QFT 线路 Clifford+T 综合优化</td>
    </tr>
    <tr>
      <td><code>cross_target_qaoa</code></td>
      <td>跨目标鲁棒 QAOA 优化（IBM &amp; IonQ）</td>
    </tr>
    <tr>
      <td rowspan="3"><b>Cryptographic</b></td>
      <td><code>AES-128 CTR</code></td>
      <td>C++ AES-128 Counter mode 吞吐量（OpenSSL 验证）</td>
    </tr>
    <tr>
      <td><code>SHA-256</code></td>
      <td>C++ SHA-256 吞吐量（OpenSSL 验证）</td>
    </tr>
    <tr>
      <td><code>SHA3-256</code></td>
      <td>C++ SHA3-256 吞吐量（OpenSSL 验证）</td>
    </tr>
    <tr>
      <td rowspan="3"><b>CommunicationEngineering</b></td>
      <td><code>LDPCErrorFloor</code></td>
      <td>使用 importance sampling 针对 trapping sets 估计 LDPC 码 error floor</td>
    </tr>
    <tr>
      <td><code>PMDSimulation</code></td>
      <td>极化模色散（PMD）仿真，针对罕见中断事件的 importance sampling</td>
    </tr>
    <tr>
      <td><code>RayleighFadingBER</code></td>
      <td>瑞利衰落信道 BER 分析，针对深衰落事件的 importance sampling</td>
    </tr>
    <tr>
      <td rowspan="2"><b>EnergyStorage</b></td>
      <td><code>BatteryFastChargingProfile</code></td>
      <td>在电压、温升和退化约束下优化锂离子电池快充电流曲线</td>
    </tr>
    <tr>
      <td><code>BatteryFastChargingSPMe</code></td>
      <td>在高保真 SPMe-T-Aging 电化学模型下优化分段快充策略</td>
    </tr>
    <tr>
      <td><b>SustainableDataCenterControl</b></td>
      <td><code>hand_written_control</code></td>
      <td>数据中心负载迁移、冷却与电池调度联合控制</td>
    </tr>
    <tr>
      <td rowspan="4"><b>ReactionOptimisation</b></td>
      <td><code>snar_multiobjective</code></td>
      <td>连续流 SnAr 反应 Pareto 优化（产量 vs. 废物）</td>
    </tr>
    <tr>
      <td><code>mit_case1_mixed</code></td>
      <td>混合变量反应收率最大化（连续工艺参数 + 离散催化剂）</td>
    </tr>
    <tr>
      <td><code>reizman_suzuki_pareto</code></td>
      <td>Suzuki 偶联 Pareto 优化（产量 vs. 催化剂周转率）</td>
    </tr>
    <tr>
      <td><code>dtlz2_pareto</code></td>
      <td>DTLZ2 Pareto 前沿逼近</td>
    </tr>
    <tr>
      <td rowspan="3"><b>MolecularMechanics</b></td>
      <td><code>weighted_parameter_coverage</code></td>
      <td>给定分子预算下的稀有力场参数覆盖优化</td>
    </tr>
    <tr>
      <td><code>diverse_conformer_portfolio</code></td>
      <td>低能量且高多样性的构象组合选择</td>
    </tr>
    <tr>
      <td><code>torsion_profile_fitting</code></td>
      <td>面向目标能量曲线的扭转参数缩放拟合</td>
    </tr>
    <tr>
      <td rowspan="16"><b>Optics</b></td>
      <td><code>adaptive_constrained_dm_control</code></td>
      <td>受约束可变形镜（DM）控制</td>
    </tr>
    <tr>
      <td><code>adaptive_temporal_smooth_control</code></td>
      <td>时序平滑与补偿质量的 AO 控制权衡</td>
    </tr>
    <tr>
      <td><code>adaptive_energy_aware_control</code></td>
      <td>能耗感知自适应光学控制</td>
    </tr>
    <tr>
      <td><code>adaptive_fault_tolerant_fusion</code></td>
      <td>容错多 WFS 斜率融合用于自适应光学控制</td>
    </tr>
    <tr>
      <td><code>phase_weighted_multispot_single_plane</code></td>
      <td>单平面加权多焦点相位 DOE</td>
    </tr>
    <tr>
      <td><code>phase_fourier_pattern_holography</code></td>
      <td>傅里叶图案全息</td>
    </tr>
    <tr>
      <td><code>phase_dammann_uniform_orders</code></td>
      <td>Dammann 光栅均匀级次优化</td>
    </tr>
    <tr>
      <td><code>phase_large_scale_weighted_spot_array</code></td>
      <td>大规模加权焦点阵列合成</td>
    </tr>
    <tr>
      <td><code>fiber_wdm_channel_power_allocation</code></td>
      <td>WDM 信道与发射功率分配</td>
    </tr>
    <tr>
      <td><code>fiber_mcs_power_scheduling</code></td>
      <td>MCS 与功率联合调度</td>
    </tr>
    <tr>
      <td><code>fiber_dsp_mode_scheduling</code></td>
      <td>接收端 DSP 模式调度</td>
    </tr>
    <tr>
      <td><code>fiber_guardband_spectrum_packing</code></td>
      <td>带保护带约束的频谱打包</td>
    </tr>
    <tr>
      <td><code>holographic_multifocus_power_ratio</code></td>
      <td>多焦点功率比控制</td>
    </tr>
    <tr>
      <td><code>holographic_multiplane_focusing</code></td>
      <td>多平面全息聚焦</td>
    </tr>
    <tr>
      <td><code>holographic_multispectral_focusing</code></td>
      <td>多光谱全息聚焦</td>
    </tr>
    <tr>
      <td><code>holographic_polarization_multiplexing</code></td>
      <td>偏振复用全息</td>
    </tr>
    <tr>
      <td rowspan="2"><b>ComputerSystems</b></td>
      <td><code>MallocLab</code></td>
      <td>高性能 C 动态内存分配器（utilization &amp; throughput）</td>
    </tr>
    <tr>
      <td><code>DuckDBWorkloadOptimization</code></td>
      <td>基于 DuckDB 官方 workload 的索引 / 物化视图选择与查询改写</td>
    </tr>
    <tr>
      <td><b>EngDesign</b></td>
      <td><code>CY_03, WJ_01, XY_05, AM_02, AM_03, YJ_02, YJ_03</code></td>
      <td>来自 <a href="https://github.com/AGI4Engineering/EngDesign">EngDesign</a> 的多学科任务：驱动器、图像去噪、CPU 逻辑、路径规划</td>
    </tr>
    <tr>
      <td rowspan="5"><b>InventoryOptimization</b></td>
      <td><code>tree_gsm_safety_stock</code></td>
      <td>树形多级安全库存配置（GSM）</td>
    </tr>
    <tr>
      <td><code>general_meio</code></td>
      <td>通用拓扑 MEIO（仿真驱动目标）</td>
    </tr>
    <tr>
      <td><code>joint_replenishment</code></td>
      <td>多 SKU 共享订货成本的联合补货优化</td>
    </tr>
    <tr>
      <td><code>finite_horizon_dp</code></td>
      <td>有限期随机库存控制（时变策略）</td>
    </tr>
    <tr>
      <td><code>disruption_eoqd</code></td>
      <td>供应中断场景下的 EOQ 批量优化</td>
    </tr>
    <tr>
      <td rowspan="3"><b>PyPortfolioOpt</b></td>
      <td><code>robust_mvo_rebalance</code></td>
      <td>含行业 / 因子 / 换手约束的鲁棒均值方差再平衡</td>
    </tr>
    <tr>
      <td><code>cvar_stress_control</code></td>
      <td>在收益与暴露约束下进行 CVaR 压力控制配置</td>
    </tr>
    <tr>
      <td><code>discrete_rebalance_mip</code></td>
      <td>带整数手数约束的离散再平衡混合整数优化</td>
    </tr>
    <tr>
      <td><b>MarketMaking</b></td>
      <td><code>InventoryAwareQuoting</code></td>
      <td>在不利选择与仓位约束下进行库存感知的 DUAL 做市报价</td>
    </tr>
    <tr>
      <td rowspan="7"><b>JobShop</b></td>
      <td><code>abz</code></td>
      <td>JSSP ABZ 家族（Adams, Balas, Zawack 1988）</td>
    </tr>
    <tr>
      <td><code>ft</code></td>
      <td>JSSP FT 家族（Fisher &amp; Thompson 1963）</td>
    </tr>
    <tr>
      <td><code>la</code></td>
      <td>JSSP LA 家族（Lawrence 1984）</td>
    </tr>
    <tr>
      <td><code>orb</code></td>
      <td>JSSP ORB 家族（Applegate &amp; Cook 1991）</td>
    </tr>
    <tr>
      <td><code>swv</code></td>
      <td>JSSP SWV 家族（Storer、Wu、Vaccari 1992）</td>
    </tr>
    <tr>
      <td><code>ta</code></td>
      <td>JSSP Taillard 家族（1993）</td>
    </tr>
    <tr>
      <td><code>yn</code></td>
      <td>JSSP YN 家族（Yamada &amp; Nakano 1992）</td>
    </tr>
    <tr>
      <td rowspan="4"><b>StructuralOptimization</b></td>
      <td><code>ISCSO2015</code></td>
      <td>在应力 / 位移约束下最小化 45 杆 2D 桁架重量</td>
    </tr>
    <tr>
      <td><code>ISCSO2023</code></td>
      <td>在离散截面约束下最小化 284 杆 3D 塔架重量</td>
    </tr>
    <tr>
      <td><code>TopologyOptimization</code></td>
      <td>MBB 梁 2D 拓扑优化（SIMP），体积约束柔度最小化</td>
    </tr>
    <tr>
      <td><code>PyMOTOSIMPCompliance</code></td>
      <td>基于 pyMOTO 的 2D 梁拓扑优化（SIMP + OC/MMA），体积分数约束</td>
    </tr>
    <tr>
      <td rowspan="6"><b>Robotics</b></td>
      <td><code>DynamicObstacleAvoidanceNavigation</code></td>
      <td>在动态环境中控制差分轮机器人从起点到终点</td>
    </tr>
    <tr>
      <td><code>QuadrupedGaitOptimization</code></td>
      <td>通过优化 8 个步态参数最大化四足机器人前向速度（MuJoCo）</td>
    </tr>
    <tr>
      <td><code>RobotArmCycleTimeOptimization</code></td>
      <td>使 7-DOF KUKA LBR iiwa 机械臂无碰撞运动时间最短（PyBullet）</td>
    </tr>
    <tr>
      <td><code>PIDTuning</code></td>
      <td>在多个飞行场景下调节 2D 四旋翼的级联 PID 控制器</td>
    </tr>
    <tr>
      <td><code>UAVInspectionCoverageWithWind</code></td>
      <td>风场扰动下的无人机巡检覆盖</td>
    </tr>
    <tr>
      <td><code>CoFlyersVasarhelyiTuning</code></td>
      <td>调优 CoFlyers 群飞系统的 Vasarhelyi 参数</td>
    </tr>
    <tr>
      <td rowspan="2"><b>Aerodynamics</b></td>
      <td><code>CarAerodynamicsSensing</code></td>
      <td>在 3D 汽车表面选择 30 个传感器位置用于压力场重建</td>
    </tr>
    <tr>
      <td><code>DawnAircraftDesignOptimization</code></td>
      <td>在巡航 / 续航 / 载荷约束下联合优化机翼、机身、动力参数以最小化飞机总重量</td>
    </tr>
    <tr>
      <td><b>WirelessChannelSimulation</b></td>
      <td><code>HighReliableSimulation</code></td>
      <td>使用 importance sampling 估计 Hamming(127,120) 的 BER</td>
    </tr>
    <tr>
      <td><b>PowerSystems</b></td>
      <td><code>EV2GymSmartCharging</code></td>
      <td>上游对齐的电动车智能充电调度</td>
    </tr>
    <tr>
      <td rowspan="2"><b>ContinuousCasting</b></td>
      <td><code>CuttingOptimization</code></td>
      <td>把连续浇铸的钢坯切成成品，最小化报废并贴近客户目标值（离线；最优可达）</td>
    </tr>
    <tr>
      <td><code>CuttingOptimizationOnline</code></td>
      <td>在线（闭环）切割：0.8m 报废段只在揭示提前量内才告知 agent——信息不对称使 agent（经验上）低于全知最优（观察结果，非严格下界证明）</td>
    </tr>
    <tr>
      <td><b>AdditiveManufacturing</b></td>
      <td><code>DiffSimThermalControl</code></td>
      <td>基于可微仿真的增材制造工艺优化</td>
    </tr>
  </tbody>
</table>
