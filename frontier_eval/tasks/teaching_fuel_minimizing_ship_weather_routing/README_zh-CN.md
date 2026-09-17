# 燃油最小化船舶气象航线规划

这个教学版任务基于 `benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting`。
它面向懂最短路、但还没有接触过船舶航线优化的读者。

## 目录结构

```text
teaching_fuel_minimizing_ship_weather_routing/
├── README.md
├── README_zh-CN.md
├── Task.md
├── Task_zh-CN.md
├── baseline/
│   └── init.py
└── verification/
    ├── reference.py
    └── evaluate.py
```

## 这个基准在教什么

这个任务要求你在冻结的沿海栅格上规划一条船舶航线，并尽量降低燃油消耗。
路径必须避开陆地，而且每条边的代价不仅取决于步长，还会受确定性的风场和流场影响。

它非常适合讲解加权最短路：
图结构是固定的，但边权来自物理模型。

## 事实来源

冻结实例和运行时辅助函数都在：

`benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/runtime/problem.py`

<!-- AI_GENERATED -->
