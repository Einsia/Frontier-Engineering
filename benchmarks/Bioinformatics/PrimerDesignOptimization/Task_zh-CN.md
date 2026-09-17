# PCR 引物设计优化（PCR Primer Design Optimization）

## 1. 问题描述（Problem）

针对一条人工合成的 DNA 模板，设计一对 PCR 引物（正向和反向）。
引物必须特异性扩增目标扩增区域，同时满足热力学和结构约束条件。

引物设计对 PCR 扩增的成功与否至关重要。设计不当的引物可能导致非特异性扩增、
引物二聚体伪迹或反应失败。

## 2. 模板与扩增区域（Template and Amplicon）

模板序列为一段 120 bp 的人工合成 DNA 片段：

```text
AAGTAAAGGCTAGTGCCCGACAAAGCGATTGTTGGGATTGTACTTGTCGGCAACGTTCCAAACG
TATGGAGGACGGGTAACGTCGGGCTAATGAATTAAGGAGCATGTAGTGCGCAGAGA
```

- **扩增起始位置（Amplicon start）**：索引 20（0-based）
- **扩增结束位置（Amplicon end）**：索引 99（0-based，包含）
- **扩增片段长度（Amplicon length）**：80 bp

正向引物必须结合到扩增区域起始处的正向链上。
反向引物必须结合到扩增区域末端模板链的反向互补序列上。

## 3. 决策变量（Decision Variables）

提交两条 DNA 序列：

- `forward_primer`：正向引物序列（5′ → 3′）
- `reverse_primer`：反向引物序列（5′ → 3′）

每条引物必须满足以下约束条件：

| 约束项（Constraint） | 范围（Range） |
|---|---|
| 长度（Length） | 18–25 bp |
| GC 含量（GC content） | 40–60% |
| 熔解温度（Melting temperature, Tm） | 50–58°C |
| 引物间最大 Tm 差（Max Tm difference） | ≤ 3°C |
| GC Clamp（3′端最后 5 碱基中的 G/C 数量） | 至少 1，至多 4 |
| 自互补性（Self-complementarity） | ≤ 6 bp 连续匹配 |
| 引物间互补性（Pair complementarity） | ≤ 6 bp 连续匹配 |
| 发夹结构茎区（Hairpin stem） | ≤ 8 bp |
| 同聚核苷酸连续重复最大值（Max homopolymer run） | ≤ 4 个相同碱基 |
| 比对特异性（Alignment） | 引物必须对齐到目标扩增区域边界 |
| 扩增产物长度（Product length） | PCR 产物长度必须在 1 到模板长度之间 |

## 4. 热力学模型（Thermodynamic Model）

熔解温度采用最邻近热力学模型（Nearest-Neighbor Model）结合 SantaLucia 盐校正公式计算：

```text
Tm = (1000 * ΔH) / (ΔS + R * ln(C) + salt_correction) - 273.15
```

- 最邻近参数来源：Breslauer et al.（1986）
- 盐校正公式：SantaLucia（1998）
- 一价阳离子浓度：50 mM
- 二价阳离子浓度：2 mM
- dNTP 浓度：0.8 mM
- DNA 浓度：50 nM

## 5. 提交格式（Submission Format）

在工作目录中编写 `submission.json` 文件：

```json
{
  "forward_primer": "CAAAGCGATTGTTGGGATTG",
  "reverse_primer": "CTTAATTCATTAGCCCGACG"
}
```

两个键均为必填。每条序列必须为大写 DNA 字符串，仅包含 A、T、C、G 四种字符。

## 6. 硬性验证门（Hard Validation Gates）

硬性验证门决定可行性。违反任何验证门的提交将获得最终得分零分，不论其质量评价指标如何。
评估器共实施 10 道硬性验证门；部分验证门包含多个检查条件。

**验证门 1 —— 字符有效性（Character validity）**
- 若任何引物包含 A、T、C、G 以外的字符，则判定为无效。

**验证门 2 —— 引物长度（Primer length）**
- 若任一引物短于最小长度（18 bp），则判定为无效。
- 若任一引物长于最大长度（25 bp），则判定为无效。

**验证门 3 —— GC 含量（GC content）**
- 若任一引物的 GC 含量低于下限（40%），则判定为无效。
- 若任一引物的 GC 含量超过上限（60%），则判定为无效。

**验证门 4 —— 熔解温度（Melting temperature）**
- 若任一引物的 Tm 超出允许范围（50–58°C），则判定为无效。
- 若两条引物之间的绝对 Tm 差值超过限值（3°C），则判定为无效。

**验证门 5 —— GC Clamp**
- 若任一引物最后 5 个碱基（3′ 端）中 G/C 碱基数少于 1 或多于 4，则判定为无效。

**验证门 6 —— 自互补性与引物间互补性（Self- and pair complementarity）**
- 若任一引物存在超过 6 bp 的连续自互补匹配，则判定为无效。
- 若正向与反向引物之间存在超过 6 bp 的连续交叉二聚体匹配，则判定为无效。

**验证门 7 —— 发夹结构（Hairpin structure）**
- 若任一引物形成超过 8 bp 的发夹结构茎区，则判定为无效。

**验证门 8 —— 同聚核苷酸连续重复（Homopolymer run）**
- 若任一引物包含 5 个或更多连续相同碱基的运行，则判定为无效。

**验证门 9 —— 比对特异性（Alignment specificity）**
- 若正向引物无法比对到扩增区域起始位置，则判定为无效。
- 若反向引物（以其反向互补形式）无法比对到扩增区域末端位置，则判定为无效。

**验证门 10 —— 扩增产物长度（Product length）**
- 若估算的 PCR 产物长度超出范围 [1, 模板长度]，则判定为无效。

不可行的提交将获得最终得分 `0.0`。

## 7. 质量评价指标（Quality Metrics）

评估器计算十项归一化的质量子分数，每项取值范围为 [0, 1]：

| # | 指标（Metric） | 质量目标（Quality target） |
|---|---|---|
| 1 | length_score | 20–22 bp |
| 2 | gc_content_score | 50% |
| 3 | tm_score | 接近最优值（55°C） |
| 4 | gc_clamp_score | 最后 3 个碱基中的 G/C 比例 |
| 5 | self_complementarity_score | 0 bp 互补性 |
| 6 | pair_complementarity_score | 0 bp 交叉二聚体互补性 |
| 7 | repeat_score | 0 bp 内部重复 |
| 8 | hairpin_score | 0 bp 发夹结构茎区 |
| 9 | mononucleotide_run_score | 0 bp 同聚核苷酸连续重复 |
| 10 | product_length_score | 80–120 bp 产物长度 |

硬性验证门（第 6 节）决定可行性。质量评价指标（第 7 节）评估并排序可行提交。

综合最终得分为：

```text
final_score = sum (weight_i * metric_sub_score_i)
```

最终得分越高越好。

## 8. 评估方法（Evaluation）

### 评估已生成的提交结果

```bash
python verification/evaluator.py --submission submission.json
```

### 运行候选优化程序并评估其输出

```bash
python verification/evaluator.py scripts/init.py
```

## 9. 参考资料（References）

- 配置文件：`references/primer_config.json`
- 基线优化程序：`scripts/init.py`
- 基线算法解（基于遗传算法）：`baseline/solution.py`
- 评估器：`verification/evaluator.py`