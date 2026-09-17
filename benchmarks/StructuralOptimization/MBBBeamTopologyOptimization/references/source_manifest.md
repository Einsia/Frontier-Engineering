# Source Manifest

- Upstream solver/formulation: `pyMOTO`
- Upstream files:
  - `examples/topology_optimization/ex_compliance.py`
  - `examples/topology_optimization/ex_self_weight.py` (`bc == 2` names the MBB-beam support style)
- Geometry provenance: the standard half-MBB beam benchmark lineage used in density-based topology optimization, including Sigmund (2001), "A 99 line topology optimization code written in Matlab".
- Frozen benchmark status: this repository vendors a reduced-size local half-MBB instance with fixed symmetry/support conditions and a fixed point load.
- License lineage: pyMOTO is released under the MIT License.
- Provenance class: literature-derived canonical geometry, locally frozen.
