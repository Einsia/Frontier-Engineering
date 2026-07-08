# PCR Primer Design Optimization

Design forward and reverse PCR primers for a synthetic DNA template.
This benchmark evaluates candidate primer pairs on melting temperature, GC content, complementarity,
and structural stability under a nearest-neighbor thermodynamic model.

## File Structure

```text
PrimerDesignOptimization/
├── README.md
├── Task.md
├── references/
│   └── primer_config.json
├── scripts/
│   └── init.py
├── baseline/
│   └── solution.py
├── verification/
│   ├── evaluator.py
│   └── requirements.txt
└── frontier_eval/
    ├── eval_command.txt
    ├── initial_program.txt
    ├── agent_files.txt
    ├── artifact_files.txt
    ├── constraints.txt
    └── run_eval.py
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r verification/requirements.txt
```

### 2. Run the Baseline Optimizer

```bash
cd benchmarks/Bioinformatics/PrimerDesignOptimization
python scripts/init.py
# Outputs: submission.json
```

### 3. Evaluate a Submission

```bash
cd benchmarks/Bioinformatics/PrimerDesignOptimization
python verification/evaluator.py --submission submission.json
```

### 4. Evaluate a Candidate Program Directly

```bash
cd benchmarks/Bioinformatics/PrimerDesignOptimization
python verification/evaluator.py scripts/init.py
```

## Submission Format

Write `submission.json` containing the candidate primer pair:

```json
{
  "forward_primer": "GCTAGCTAGCTAGCTAGCT",
  "reverse_primer": "GCTAGCTAGCTAGCTAGCT"
}
```

Both keys are required. Each primer must be an uppercase DNA string consisting only of the characters A, T, C, and G.

## Task Summary

- **Template**: 120 bp synthetic DNA sequence
- **Amplicon region**: bases 21–100 (80 bp target)
- **Primer length**: 18–25 bp
- **GC content**: 40–60%
- **Melting temperature**: 50–58°C (optimal 55°C)
- **Max Tm difference**: 3°C between primers
- **Thermodynamics**: Nearest-neighbor model (SantaLucia 1998)
- **Salt conditions**: 50 mM monovalent, 2 mM divalent, 0.8 mM dNTP

## Scoring

Hard validation gates determine feasibility. Among feasible candidates,
ten weighted quality metrics rank primer pairs.

The ten quality metrics are:

- **tm_score**: proximity to optimal melting temperature
- **gc_content_score**: proximity to 50% GC content
- **length_score**: proximity to 20–22 bp primer length
- **gc_clamp_score**: G/C fraction in the last 3 bases (3′ end)
- **self_complementarity_score**: degree of self-complementarity
- **pair_complementarity_score**: degree of cross-dimer complementarity
- **repeat_score**: degree of internal sequence repeats
- **hairpin_score**: degree of hairpin structure
- **mononucleotide_run_score**: degree of homopolymer runs
- **product_length_score**: proximity to preferred product length

An infeasible submission (one that violates any hard validation gate) receives a final score of zero.
Higher final score is better.

## Run with frontier_eval (unified)

Unified benchmark: `task=unified task.benchmark=Bioinformatics/PrimerDesignOptimization`

```bash
python -m frontier_eval \
task=unified task.benchmark=Bioinformatics/PrimerDesignOptimization \
algorithm.iterations=10
```
