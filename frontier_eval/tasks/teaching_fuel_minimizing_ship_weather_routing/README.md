# Fuel-Minimizing Ship Weather Routing

This teaching scaffold is derived from `benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting`.
It explains a grid-routing problem with wind and current fields for readers who know shortest paths but are new to maritime routing.

## Directory Structure

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

## What This Benchmark Teaches

The benchmark asks you to route a ship across a frozen coastal grid while minimizing fuel usage.
Moving is constrained by land, and the edge cost depends on the deterministic wind and current fields.

This is a nice teaching example of weighted shortest-path planning:
the graph is fixed, but the edge weights come from the physics model.

## Source of Truth

The frozen instance and runtime helpers live in:

`benchmarks/OperationsResearch/FuelMinimizingShipWeatherRouting/runtime/problem.py`

<!-- AI_GENERATED -->
