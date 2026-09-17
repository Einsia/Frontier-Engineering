# NCAAInsertion - 非规范氨基酸插入设计

## 一句话解释

在蛋白质的指定位置插入非标准氨基酸 TRF（N1-甲酰基色氨酸），并重新设计周围残基来稳定结构。

## 生物学背景

大多数 AI 蛋白质设计模型（如 ProteinMPNN）只认得 20 种标准氨基酸，无法处理非规范氨基酸（NCAA）。Rosetta 基于物理方程计算能量，可以处理任意非标准氨基酸——这是它的独特优势。

本任务对应 Agent Rosetta 论文（arXiv:2603.15952, ICML 2026）的 Case B。

## 运行方式

```bash
cd benchmarks/ProteinDesign/NCAAInsertion
mkdir -p outputs
python verification/evaluator.py prepare --raw-task data/raw_task.json --prepared-output outputs/prepared.pdb
python scripts/init.py --prepared-input outputs/prepared.pdb --solution-output outputs/solution.pdb
python verification/evaluator.py evaluate --native outputs/prepared.pdb --candidate outputs/solution.pdb --result-output outputs/result.json
```

## 统一 benchmark ID

`ProteinDesign/NCAAInsertion`

## 环境准备

```bash
docker pull rosettacommons/rosetta:serial
```
