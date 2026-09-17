# 任务：依赖感知的网络安全补丁调度

请在 `scripts/init.py` 中实现 `solve(instance)`。函数必须返回可 JSON 序列化的对象，并且对象只能包含 `schedule` 字段。

日程格式为 `{'schedule': [{'patch_id': 'P000', 'start_slot': 0}, ...]}`。每个条目必须且只能包含 `patch_id` 与 `start_slot`。补丁标识符必须存在于实例中，开始时隙必须是非负整数，同一补丁最多出现一次。未列出的补丁视为未应用。

## 调度语义

所选补丁占用半开区间 `[start_slot, start_slot + duration)`。执行不可抢占，完成时隙由实例中的工期推导。

提交的日程必须满足以下全部条件：

- 每个补丁不晚于 `horizon` 完成。
- 选择补丁时，必须选择其全部直接和传递前置补丁。
- 每个直接前置补丁必须不晚于依赖补丁开始时完成。
- 补丁的完整执行区间必须包含在每个受影响资产以及每个服务需求所列服务的至少一个维护窗口内。
- 当资产的 `exclusive_change` 为 true 时，影响该资产的补丁不能重叠。
- 每个时隙内，每类可再生资源的总需求不能超过该时隙容量。
- 每个时隙内，每个服务的总停机需求不能超过该时隙容量。
- 每个服务在整个规划期内的总停机单位不能超过其维护预算。

所有工期、关系、需求和成本均以实例数据为准。候选程序提供的完成时间、成本或可行性声明不会被接受。

## 目标函数

最小化以微货币单位表示的总期望损失。

每个漏洞的修复时间是任一覆盖该漏洞的已选补丁的最早完成时隙。若没有覆盖补丁完成，则修复时间为规划期末。安全损失使用修复前所有时隙的利用概率。漏洞影响先乘以 `criticality_ppm` 调整；累计利用概率通过按 1,000,000 比例反复乘以“未被利用”的概率得到。

业务损失是在每个已选补丁、服务需求及占用时隙上累加 `downtime_units * loss_microunits_by_slot[t]`。每个已选补丁的回滚损失是 `rollback_probability_ppm * rollback_impact_microunits / 1,000,000` 的四舍五入整数值。

验证器仅根据实例与日程独立重算可行性和原始目标值。原始值越低越好。框架使用 `log2(baseline_raw / candidate_raw)` 进行归一化；该计算不属于 `solve` 或 `evaluate_solution`。

## 确定性与隔离

对于同一实例，`solve` 必须具有确定性。它不得读取文件、访问网络、检查环境变量或秘密、使用评估器输出，也不得依赖隐藏种子值。`scripts/init.py` 所需的所有导入必须放在 `solve` 函数内部。

所提供的起始实现是一个可行、自包含的基线。你可以替换其内部启发式算法，但必须保留函数签名和输出结构。

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## 输入 Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "instance_id",
    "tier",
    "horizon",
    "probability_scale",
    "assets",
    "services",
    "resources",
    "vulnerabilities",
    "patches"
  ],
  "properties": {
    "instance_id": {
      "type": "string",
      "minLength": 1
    },
    "tier": {
      "type": "string",
      "enum": [
        "small",
        "medium",
        "large"
      ]
    },
    "horizon": {
      "type": "integer",
      "minimum": 1
    },
    "probability_scale": {
      "type": "integer",
      "enum": [
        1000000
      ]
    },
    "assets": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "asset_id",
          "exclusive_change",
          "maintenance_windows"
        ],
        "properties": {
          "asset_id": {
            "type": "string",
            "minLength": 1
          },
          "exclusive_change": {
            "type": "boolean"
          },
          "maintenance_windows": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "start_slot",
                "end_slot"
              ],
              "properties": {
                "start_slot": {
                  "type": "integer",
                  "minimum": 0
                },
                "end_slot": {
                  "type": "integer",
                  "minimum": 1
                }
              }
            }
          }
        }
      }
    },
    "services": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "service_id",
          "maintenance_windows",
          "downtime_capacity_by_slot",
          "downtime_budget",
          "loss_microunits_by_slot"
        ],
        "properties": {
          "service_id": {
            "type": "string",
            "minLength": 1
          },
          "maintenance_windows": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "start_slot",
                "end_slot"
              ],
              "properties": {
                "start_slot": {
                  "type": "integer",
                  "minimum": 0
                },
                "end_slot": {
                  "type": "integer",
                  "minimum": 1
                }
              }
            }
          },
          "downtime_capacity_by_slot": {
            "type": "array",
            "items": {
              "type": "integer",
              "minimum": 0
            }
          },
          "downtime_budget": {
            "type": "integer",
            "minimum": 0
          },
          "loss_microunits_by_slot": {
            "type": "array",
            "items": {
              "type": "integer",
              "minimum": 0
            }
          }
        }
      }
    },
    "resources": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "resource_id",
          "capacity_by_slot"
        ],
        "properties": {
          "resource_id": {
            "type": "string",
            "minLength": 1
          },
          "capacity_by_slot": {
            "type": "array",
            "items": {
              "type": "integer",
              "minimum": 0
            }
          }
        }
      }
    },
    "vulnerabilities": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "vulnerability_id",
          "asset_id",
          "impact_microunits",
          "criticality_ppm",
          "exploit_probability_ppm_by_slot"
        ],
        "properties": {
          "vulnerability_id": {
            "type": "string",
            "minLength": 1
          },
          "asset_id": {
            "type": "string",
            "minLength": 1
          },
          "impact_microunits": {
            "type": "integer",
            "minimum": 1
          },
          "criticality_ppm": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000000
          },
          "exploit_probability_ppm_by_slot": {
            "type": "array",
            "items": {
              "type": "integer",
              "minimum": 0,
              "maximum": 1000000
            }
          }
        }
      }
    },
    "patches": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "patch_id",
          "duration",
          "prerequisite_patch_ids",
          "affected_asset_ids",
          "covered_vulnerability_ids",
          "resource_demands",
          "service_demands",
          "rollback_probability_ppm",
          "rollback_impact_microunits"
        ],
        "properties": {
          "patch_id": {
            "type": "string",
            "minLength": 1
          },
          "duration": {
            "type": "integer",
            "minimum": 1
          },
          "prerequisite_patch_ids": {
            "type": "array",
            "uniqueItems": true,
            "items": {
              "type": "string",
              "minLength": 1
            }
          },
          "affected_asset_ids": {
            "type": "array",
            "uniqueItems": true,
            "items": {
              "type": "string",
              "minLength": 1
            }
          },
          "covered_vulnerability_ids": {
            "type": "array",
            "uniqueItems": true,
            "items": {
              "type": "string",
              "minLength": 1
            }
          },
          "resource_demands": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "resource_id",
                "units"
              ],
              "properties": {
                "resource_id": {
                  "type": "string",
                  "minLength": 1
                },
                "units": {
                  "type": "integer",
                  "minimum": 0
                }
              }
            }
          },
          "service_demands": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "service_id",
                "downtime_units"
              ],
              "properties": {
                "service_id": {
                  "type": "string",
                  "minLength": 1
                },
                "downtime_units": {
                  "type": "integer",
                  "minimum": 0
                }
              }
            }
          },
          "rollback_probability_ppm": {
            "type": "integer",
            "minimum": 0,
            "maximum": 1000000
          },
          "rollback_impact_microunits": {
            "type": "integer",
            "minimum": 0
          }
        }
      }
    }
  }
}
```

## 输出 Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schedule"
  ],
  "properties": {
    "schedule": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "patch_id",
          "start_slot"
        ],
        "properties": {
          "patch_id": {
            "type": "string",
            "minLength": 1
          },
          "start_slot": {
            "type": "integer",
            "minimum": 0
          }
        }
      }
    }
  }
}
```

## 约束与目标

输出必须满足上文全部硬约束。冻结验证器会独立检查可行性并重算
`verifier_recomputed_total_expected_monetary_loss_microunits`；优化目标是将这个严格为正的原始指标最小化。
有效实例使用相对基线的 `log2` 改进值，并取平均；无效方案得分为 `-1e18`。
问题设定为 `离线批量`。目标设计理由：Expected monetary loss is appropriate because patching is not valuable merely for maximizing patch count or minimizing completion time. It prices the security exposure retained by delaying or omitting patches while also charging for the business disruption and rollback exposure caused by applying them. Expressing all three components in a common monetary unit produces a continuous, auditable tradeoff and keeps feasibility rules separate from preferences. The raw objective is strictly lower-is-better and can be kept positive through instance construction, making it suitable for framework-owned log2_baseline_ratio normalization.
文献对齐：NIST SP 800-40 Rev. 4 frames enterprise patching as risk-based preventive maintenance that must be planned alongside operational constraints. CISA BOD 22-01 provides a concrete basis for prioritizing vulnerabilities with evidence of active exploitation and for modeling remediation deadlines. This benchmark turns those planning principles into a deterministic offline optimization problem; its synthetic monetary loss, rollback, resource, and downtime parameters are benchmark abstractions rather than values claimed by either source. It differs from classical makespan scheduling by allowing economically rational patch omission and by jointly enforcing dependency closure, maintenance calendars, renewable resources, and service downtime limits.
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
