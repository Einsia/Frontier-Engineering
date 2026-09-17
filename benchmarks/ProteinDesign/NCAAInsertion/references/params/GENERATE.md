# TRF.params 生成说明

## TRF 是什么

TRF = N1-甲酰基色氨酸（N1-formyl-tryptophan），是色氨酸的衍生物，在吲哚环 N1 位置有一个甲酰基（-CHO）。

SMILES: `c1ccc2c(c1)c(c[n](C=O)2)CC(C(=O)O)N`

## 文件清单

| 文件 | 说明 |
|:-----|:------|
| `TRF.params` | Rosetta 残基参数文件（手动生成，见下方说明） |
| `TRF.sdf` | TRF 的 3D 结构文件（RDKit 从 SMILES 生成） |
| `GENERATE.md` | 本文件 |

## 当前 TRF.params 的生成方式

`rosetta_py` 模块是 Rosetta's `molfile_to_params_polymer.py` 的依赖项，
该模块**不包含在 Rosetta 公开源码分发版中**。
因此无法在公开环境下使用 Rosetta 官方脚本生成 TRF.params。

当前 `TRF.params` 基于 Rosetta 内置的 `n-in-methyl-tryptophan.params` 手动修改，
将甲基（-CH3）替换为甲酰基（-CHO），并调整了原子类型、键参数和电荷。

经实际测试验证：
1. ✅ PyRosetta 能正确加载 TRF.params
2. ✅ TRF 能在 4 个测试蛋白中正确放置（trf_present = true）
3. ✅ Rosetta ref2015 评分正常
4. ✅ 原子数量与 RDKit 生成的 3D 结构一致

对于 benchmark 而言，params 文件的一致性比绝对精确性更重要——
所有 agent 都使用同一份 params，比较结果公平有效。

## 使用 Rosetta 官方工具重新生成（需完整 Rosetta 源码）

如需用官方工具重新生成，需要获取包含 `rosetta_py` 模块的完整 Rosetta 源码
（需向 RosettaCommons 申请学术或商业许可）：

```bash
python $ROSETTA/main/source/scripts/python/public/molfile_to_params_polymer.py \
    --polymer --name TRF \
    --use-parent-rotamers TRP \
    -i TRF.sdf
```

## 验证方法

在 PyRosetta 中验证 params 可正确加载：

```python
import pyrosetta
pyrosetta.init(silent=True, extra_options="-extra_res_fa TRF.params")
res_set = pyrosetta.rosetta.core.chemical.ChemicalManager.get_instance().residue_type_set("fa_standard")
assert res_set.has_name("TRF"), "TRF params not loaded"
```
