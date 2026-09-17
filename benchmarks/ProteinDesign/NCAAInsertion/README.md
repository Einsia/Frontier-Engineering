# NCAAInsertion

## Quick Start

```bash
cd benchmarks/ProteinDesign/NCAAInsertion
mkdir -p outputs
python verification/evaluator.py prepare --raw-task data/raw_task.json --prepared-output outputs/prepared.pdb
python scripts/init.py --prepared-input outputs/prepared.pdb --solution-output outputs/solution.pdb
python verification/evaluator.py evaluate --native outputs/prepared.pdb --candidate outputs/solution.pdb --result-output outputs/result.json
```

## Unified Benchmark ID

`ProteinDesign/NCAAInsertion`

## Environment

```bash
docker pull rosettacommons/rosetta:serial
```
