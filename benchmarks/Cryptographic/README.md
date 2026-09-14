# Cryptographic Benchmarks

This domain contains algorithm-acceleration tasks for:

- `AES-128 CTR`
- `SHA-256`
- `SHA3-256`

Each task provides:

- baseline C++ implementation (`baseline/*.cpp`)
- correctness verification (the scorer's own FIPS/NIST references; `verification/validate.cpp` is a standalone developer check)
- throughput benchmark (measured by the scorer, which re-checks the output of every timed iteration; `verification/evaluate.cpp` is a standalone developer check)
- reference PDF (`references/*.pdf`)

## Run with frontier_eval (unified)

```bash
# AES-128
python -m frontier_eval task=unified task.benchmark=Cryptographic/AES-128 algorithm.iterations=10

# SHA-256
python -m frontier_eval task=unified task.benchmark=Cryptographic/SHA-256 algorithm.iterations=10

# SHA3-256
python -m frontier_eval task=unified task.benchmark=Cryptographic/SHA3-256 algorithm.iterations=10
```

Backwards-compatible aliases (route to the same unified benchmark via config): `task=crypto_aes128`, `task=crypto_sha256`, `task=crypto_sha3_256`.

Optional reference injection for agents (default: disabled):

```bash
python -m frontier_eval task=crypto_sha256 task.include_pdf_reference=true
```
