# CacheReplacement — Data

This directory contains external data required by the CacheReplacement benchmark.

## Traces

ChampSim trace files generated from SPEC CPU 2017 workloads.

**Source**: [DPC-3 public repository](https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/)

> ⚠️ **License**: This benchmark does NOT redistribute SPEC CPU traces.
> Users must download traces from the original source and verify integrity.

### Download

```bash
# Automated download + checksum verification
bash data/download_traces.sh
```

### Verify

```bash
# Verify all 10 traces match expected checksums
cd data/traces && sha256sum -c ../checksums.txt
```

### Trace list

| Trace | Domain | Quick | Full | Size (xz) |
|---|---|---|---|---|
| `603.bwaves_s-3699B` | Float (scientific) | — | ✓ | ~50 MB |
| `605.mcf_s-665B` | Integer (combinatorial) | ✓ | ✓ | ~60 MB |
| `625.x264_s-18B` | Integer (video) | ✓ | ✓ | ~80 MB |
| `654.roms_s-842B` | Float (ocean) | — | ✓ | ~55 MB |
| `657.xz_s-3167B` | Integer (compression) | — | ✓ | ~70 MB |
| `600.perlbench_s-210B` | Integer (scripting) | — | ✓ | ~60 MB |
| `602.gcc_s-734B` | Integer (compiler) | — | ✓ | ~75 MB |
| `607.cactuBSSN_s-2421B` | Float (physics) | ✓ | ✓ | ~90 MB |
| `621.wrf_s-575B` | Float (weather) | — | ✓ | ~65 MB |
| `631.deepsjeng_s-928B` | Integer (AI/game) | — | ✓ | ~55 MB |

**Total**: ~660 MB compressed, ~3 GB decompressed.

## Simulator

ChampSim is auto-cloned to `data/ChampSim/` at commit `51588e1d`.
Source: https://github.com/ChampSim/ChampSim

## Structure

```
data/
├── README.md              ← this file
├── download_traces.sh     ← automated download script
├── checksums.txt          ← SHA256 checksums for all traces
├── traces/                ← .xz trace files (NOT tracked in git)
└── ChampSim/              ← simulator source (NOT tracked in git)
```
