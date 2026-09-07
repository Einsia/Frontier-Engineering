# Malloc Lab Experiment

The experiment content is from [Tsinghua University Computer Systems 2023 Malloc Lab](https://github.com/PKUanonym/REKCARC-TSC-UHT/tree/master/%E5%A4%A7%E4%BA%8C%E4%B8%8A/%E8%AE%A1%E7%AE%97%E6%9C%BA%E7%B3%BB%E7%BB%9F%E6%A6%82%E8%AE%BA/hw/2023). 
The relevant files are located in `benchmarks/ComputerSystems/MallocLab/malloclab-handout`. 
For more details, please see [Task](Task.md).

Note: the evolved candidate file is `malloclab-handout/mm.c`. Keep function signatures unchanged, and keep `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` markers in place so evolution algorithms can safely apply diffs.

## How the score reaches the grader

`mm.c` is compiled into `mdriver`, so anything `mdriver` prints is something
your allocator could also have printed. The score therefore does not travel
over stdout. `mdriver` writes a JSON record to the path given by `-o`, stamped
with a per-run token the grader hands it on stdin and takes away before the
first allocator call. The grader scores that record and nothing else.

Two consequences for your allocator:

* Printing your own `Score = ... = N/100` line has no effect.
* `mm.c` must not read stdin. If the token is gone by the time `main()` looks
  for it, the run is aborted and scored zero.

This closes the channel, not the process boundary: your code and the grading
code share an address space, and that is inherent to the task -- an allocator
has to run inside the program whose allocations are being measured. The
benchmark is scored on the understanding that submissions are honest
allocators. See `frontier_eval/known_exploit_token_replay.c` for the case that
is knowingly left open.
