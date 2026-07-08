# PCR 引物设计优化（PCR Primer Design Optimization）

基于人工合成的 DNA 模板，设计正向与反向 PCR 引物。
该 Benchmark 通过熔解温度（Tm）、GC 含量、互补性及结构稳定性，
在最邻近热力学模型下对候选引物对进行评估。

## 文件结构（File Structure）

```text
PrimerDesignOptimization/
├── README.md
├── Task.md
├── references/
│   └── primer_config.json
├── scripts/
│   └── init.py
├── baseline/
│   └── solution.py
├── verification/
│   ├── evaluator.py
│   └── requirements.txt
└── frontier_eval/
    ├── eval_command.txt
    ├── initial_program.txt
    ├── agent_files.txt
    ├── artifact_files.txt
    ├── constraints.txt
    └── run_eval.py
```

## 快速开始（Quick Start）

### 1. 安装依赖

```bash
pip install -r verification/requirements.txt
```

### 2. 运行基线优化程序

```bash
cd benchmarks/Bioinformatics/PrimerDesignOptimization
python scripts/init.py
# 输出：submission.json
```

### 3. 评估提交结果

```bash
cd benchmarks/Bioinformatics/PrimerDesignOptimization
python verification/evaluator.py --submission submission.json
```

### 4. 直接评估候选程序

```bash
cd benchmarks/Bioinformatics/PrimerDesignOptimization
python verification/evaluator.py scripts/init.py
```

## 提交格式（Submission Format）

编写 `submission.json` 文件，包含候选引物对：

```json
{
  "forward_primer": "GCTAGCTAGCTAGCTAGCT",
  "reverse_primer": "GCTAGCTAGCTAGCTAGCT"
}
```

两个键均为必填。每条引物必须为大写 DNA 字符串，仅包含 A、T、C、G 四种字符。

## 任务概要（Task Summary）

- **模板（Template）**：120 bp 人工合成 DNA 序列
- **扩增区域（Amplicon region）**：碱基 21–100（目标 80 bp）
- **引物长度（Primer length）**：18–25 bp
- **GC 含量（GC content）**：40–60%
- **熔解温度（Melting temperature）**：50–58°C（最优 55°C）
- **引物间最大 Tm 差（Max Tm difference）**：3°C
- **热力学模型（Thermodynamics）**：最邻近模型（SantaLucia 1998）
- **盐浓度条件（Salt conditions）**：50 mM 一价阳离子、2 mM 二价阳离子、0.8 mM dNTP

## 评分（Scoring）

硬性验证门（Hard Validation Gates）决定可行性（feasibility）。在可行候选方案中，
十项加权质量评价指标（Weighted Quality Metrics）对引物对进行排序。

十项质量评价指标如下：

- **tm_score**：接近最优熔解温度的程度
- **gc_content_score**：接近 50% GC 含量的程度
- **length_score**：接近 20–22 bp 引物长度的程度
- **gc_clamp_score**：最后 3 个碱基（3′ 端）中 G/C 的比例
- **self_complementarity_score**：自互补性程度
- **pair_complementarity_score**：引物间二聚体互补性程度
- **repeat_score**：内部序列重复程度
- **hairpin_score**：发夹结构程度
- **mononucleotide_run_score**：同聚核苷酸连续重复（Homopolymer Run）程度
- **product_length_score**：接近偏好扩增产物长度的程度

违反任何硬性验证门的提交（不可行提交）将获得最终得分（final_score）零分。得分越高越好。

## 使用 frontier_eval（统一）运行

统一 Benchmark：`task=unified task.benchmark=Bioinformatics/PrimerDesignOptimization`

```bash
python -m frontier_eval \
task=unified task.benchmark=Bioinformatics/PrimerDesignOptimization \
algorithm.iterations=10
```