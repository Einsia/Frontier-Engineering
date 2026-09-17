# Related Work — Cache Replacement Policies

## Key Papers

### LRU (Least Recently Used)

Classic baseline replacement policy. Assumes temporal locality. Used as default baseline in virtually all replacement research.

### SRRIP / DRRIP (Re-Reference Interval Prediction)

Jaleel, A., Theobald, K. B., Steely, S. C., & Emer, J.
**"High Performance Cache Replacement Using Re-Reference Interval Prediction (RRIP)."**
*Proceedings of the 37th Annual International Symposium on Computer Architecture (ISCA)*, 2010.
DOI: [10.1145/1815961.1815971](https://doi.org/10.1145/1815961.1815971)

### SHIP (Signature-based Hit Predictor)

Wu, C.-J., Jaleel, A., Hasenplaugh, W., Martonosi, M., Steely, S. C., & Emer, J.
**"SHiP: Signature-based Hit Predictor for High Performance Caching."**
*Proceedings of the 44th Annual IEEE/ACM International Symposium on Microarchitecture (MICRO)*, 2011.
DOI: [10.1145/2155620.2155671](https://doi.org/10.1145/2155620.2155671)

### Hawkeye

Jain, A., & Lin, C.
**"Hawkeye: Efficiently Identifying Access Patterns for Optimal Cache Replacement."**
*Proceedings of the Twenty-First International Conference on Architectural Support for Programming Languages and Operating Systems (ASPLOS)*, 2016.
DOI: [10.1145/2872362.2872406](https://doi.org/10.1145/2872362.2872406)

### TAGE-SC-L

Seznec, A.
**"Tage-SC-L Branch Predictors."**
*Championship Branch Prediction (CBP)*, 2016.

### ChampSim Simulator

Gober, N., Chacon, G., Wang, L., Gratz, P. V., Jimenez, D. A., Teran, E., Pugsley, S., & Kim, J.
**"The Championship Simulator: Architectural Simulation for Education and Competition."**
arXiv:2210.14324, 2022.
DOI: [10.48550/arXiv.2210.14324](https://doi.org/10.48550/arXiv.2210.14324)
GitHub: https://github.com/ChampSim/ChampSim

## Competitions

- **CRC-2** (Cache Replacement Championship 2, ISCA 2017)
  https://crc2.ece.tamu.edu/

- **DPC-3** (Data Prefetching Championship 3, ISCA 2019)
  https://dpc3.compas.cs.stonybrook.edu/

- **CBP-6** (Championship Branch Prediction 6, ISCA 2025)
  https://ericrotenberg.wordpress.ncsu.edu/cbp2025-simulator-framework/

## Trace Sources

- SPEC CPU 2017 traces for ChampSim (DPC-3 public mirror):
  https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/

- CRC-2 traces:
  http://bit.ly/2t2nkUj
