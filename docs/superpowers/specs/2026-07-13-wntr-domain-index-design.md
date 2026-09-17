# WNTR domain index compliance design

## Scope

Update only the WaterDistribution domain overview documents so they include the
required sub-task index. Do not change candidate isolation, evaluation behavior,
metadata, dependencies, or task-level documentation.

## Changes

- Add a `Tasks` section to `benchmarks/WaterDistribution/README.md` linking to
  `PumpScheduling/README.md` with a one-sentence English description.
- Add the equivalent `任务列表` section to
  `benchmarks/WaterDistribution/README_zh-CN.md`.

## Verification

Check that both relative links resolve and that the working tree contains only
the intended documentation changes after the design commit.
