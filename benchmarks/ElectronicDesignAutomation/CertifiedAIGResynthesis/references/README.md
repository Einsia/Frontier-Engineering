# References and design rationale

- The [AIGER format and tool distribution](https://fmv.jku.at/aiger/) defines the
  literal and ASCII AIG representation used by the benchmark.
- The [EPFL combinational benchmark suite](https://www.epfl.ch/labs/lsi/page-102566-en-html/benchmarks/)
  illustrates the arithmetic and control-oriented AIG workloads commonly used to
  evaluate logic-synthesis flows.
- *E-morphic* ([arXiv:2504.11574](https://arxiv.org/abs/2504.11574)) motivates
  equality saturation as an active approach to scalable circuit optimization.
- *DAG-aware AIG rewriting orchestration* ([arXiv:2310.07846](https://arxiv.org/abs/2310.07846))
  motivates evaluating rewrite scheduling on the shared graph rather than adding
  isolated per-rule gains.

The benchmark does not redistribute third-party circuits or software. Its five
circuits are deterministic, repository-owned Boolean front ends specified by
`problem_config.json` and implemented in the frozen evaluator. The cited suites
and papers provide representation, workload, and research context.
