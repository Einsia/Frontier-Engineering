# 任务：安全约束电力调度

## 背景

电力系统调度需要在降低发电成本的同时满足交流网络物理约束，并保证线路
故障后仍然可行。只针对完整电网设计的低成本方案，可能在 N-1 故障后造成
线路过载、电压越界或潮流不收敛。

本任务使用三个 PGLib-OPF 电网和12个确定性场景，覆盖正常运行、负荷变化
以及经过 AC-OPF 验证的单线路故障。

## 可编辑程序

只允许修改 `scripts/init.py` 中 `EVOLVE-BLOCK-START` 与
`EVOLVE-BLOCK-END` 之间的逻辑，并保持接口：

```python
def solve(case: dict) -> dict:
    ...
```

每个场景调用一次，返回：

```python
{
    "pg_mw": [每台发电机的有功设定值],
    "vg_pu": [每台发电机的电压幅值设定值],
}
```

两个列表必须与 `case["generators"]` 等长且全部为有限数值。同一母线上的
在线机组必须采用相同电压设定值。

## 输入

`case` ??????????????

- `case_id: str`?PGLib ?????
- `scenario_id: str`???????????
- `base_mva: float`?????????? MVA?
- `load_scale: float`?????????????
- `outage_branch: int | None`???????????????????
  ????? `None`?
- `total_active_load_mw: float`????????????????
- `buses: list[dict]`?? MATPOWER ?????????
- `generators: list[dict]`?? MATPOWER ??????????????
  ?????????
- `branches: list[dict]`????????? MATPOWER ?????????

`case["buses"]` ?????????

- `bus_id: int`?`type: int`?
- `pd_mw: float`?`qd_mvar: float`?
- `base_kv: float`?
- `vmin_pu: float`?`vmax_pu: float`?

`case["generators"]` ?????????

- `index: int`?`bus_id: int`?`online: bool`?
- `pmin_mw: float`?`pmax_mw: float`?
- `qmin_mvar: float`?`qmax_mvar: float`?
- `baseline_pg_mw: float`?`baseline_vg_pu: float`?
- `cost_model: list[float]`?????? MATPOWER `gencost` ??

`cost_model` ?????? MATPOWER ??????????
`[2, startup, shutdown, n, c_(n-1), ..., c_0]`?????????????
????????
`[1, startup, shutdown, n, x_1, y_1, ..., x_n, y_n]`?

`case["branches"]` ?????????

- `index: int`?`from_bus: int`?`to_bus: int`?
- `resistance_pu: float`?`reactance_pu: float`?`charging_pu: float`?
- `rate_a_mva: float`?`0` ?????? `RATE_A` ????
- `tap_ratio: float`?`phase_shift_deg: float`?
- `in_service: bool`?
- `angle_min_deg: float`?`angle_max_deg: float`?

Baseline 是可行但刻意次优的起点，不是参考最优答案。

## 硬约束

候选方案必须在全部场景中满足：

1. 牛顿交流潮流收敛；
2. 发电机有功、无功不越界；
3. 母线电压幅值不越界；
4. 每条有额定容量的在线支路两端视在功率不超过 `RATE_A`；
5. 支路相角差满足 `ANGMIN` 与 `ANGMAX`；
6. 输出形状正确且为有限值，每个场景两秒内返回。

任一硬约束失败都会令总体 `valid=0`、`combined_score=0`。

## 场景

使用 IEEE RTS 24母线、IEEE 57母线和 IEEE RTS 73母线系统。每个系统包含：

- 98%负荷、完整电网；
- 100%负荷、完整电网；
- 100%负荷、线路故障A；
- 102%负荷、线路故障B。

## 评分

每个可行场景计算三个归一化分量：

```text
cost_efficiency = min(1.05, 参考AC-OPF成本 / 候选成本)
thermal_margin  = clip((100 - 最大支路负载率) / 20, 0, 1)
voltage_margin  = 母线电压到上下限归一化距离的第10百分位

scenario_score = 70 * cost_efficiency
               + 20 * thermal_margin
               + 10 * voltage_margin
```

总分：

```text
combined_score = 0.75 * 场景平均分 + 0.25 * 场景最低分
```

分数越高越好。成本项奖励接近冻结 AC-OPF 参考成本，另外两项奖励不贴近
热容量或电压边界的安全调度。

## 禁止行为

- 不得修改验证器、PGLib案例、场景清单或元数据；
- `solve` 不得读写文件、启动子进程、访问网络或依赖当前时间；
- 不得硬编码验证器输出或绕过交流潮流；
- 策略必须确定性执行。
