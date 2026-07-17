# MarketMaking

This domain contains lightweight, deterministic market-making control tasks inspired by
dual-listed equity trading. Each synthetic company has a liquid primary listing and a less
liquid `DUAL` listing that share the same latent fair value.

The benchmarks are fully offline and do not connect to a real exchange. They preserve the
engineering trade-offs that matter for market makers: spread capture, adverse selection,
inventory control, cross-market dislocations, changing liquidity, and risk constraints.

## Task

- `InventoryAwareQuoting`: quote the DUAL listings while controlling inventory across changing
  liquidity, volatility, order-flow, and basis regimes.

The task uses three synthetic pairs named after familiar equities:

- `NVDA` / `NVDA_DUAL`
- `JPM` / `JPM_DUAL`
- `AMZN` / `AMZN_DUAL`

The names are scenario labels only; no real market data is bundled or requested.
