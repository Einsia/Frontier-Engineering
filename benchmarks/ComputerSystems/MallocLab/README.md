# Malloc Lab Experiment

The experiment content is from [Tsinghua University Computer Systems 2023 Malloc Lab](https://github.com/PKUanonym/REKCARC-TSC-UHT/tree/master/%E5%A4%A7%E4%BA%8C%E4%B8%8A/%E8%AE%A1%E7%AE%97%E6%9C%BA%E7%B3%BB%E7%BB%9F%E6%A6%82%E8%AE%BA/hw/2023). 
The relevant files are located in `benchmarks/ComputerSystems/MallocLab/malloclab-handout`. 
For more details, please see [Task](Task.md).

Note: the evolved candidate file is `malloclab-handout/mm.c`. Keep function signatures unchanged, and keep `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END` markers in place so evolution algorithms can safely apply diffs.

Official scoring uses a Wasm64 allocator with a trusted host driver. Install the Linux x86-64 toolchain once from the repository root:

```bash
python benchmarks/_shared/malloc_wasm/setup.py --install
bash benchmarks/ComputerSystems/MallocLab/frontier_eval/run_eval.sh python3 benchmarks/ComputerSystems/MallocLab
```

The score measures calls in the isolated runtime; native `make && ./mdriver -V` remains available for local debugging. The runtime keeps 64-bit pointers and the 20 MiB simulated heap. It requires Linux user namespaces, bubblewrap, and a native C compiler. `FRONTIER_MALLOC_TOOLCHAIN` selects an alternate toolchain installation directory.
