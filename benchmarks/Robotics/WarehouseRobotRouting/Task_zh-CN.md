# 任务：仓储机器人路径规划

请在 `scripts/init.py` 中实现 `solve(instance)`。

## 输入

输入对象包含：

- `instance_id`：非空实例标识。
- `graph.nodes`：全部合法节点标识。
- `graph.edges`：无向可通行边，每条边由两个节点标识表示。
- `robots`：机器人对象，字段为 `id`、`start_node` 和正整数 `capacity`。
- `orders`：订单对象，字段为 `id`、`pickup_node`、`dropoff_node` 和正整数 `weight`。
- `horizon`：离散规划的最终时刻 `H`。

## 输出

返回对象只能包含顶层字段 `robots`。该数组必须恰好包含每台输入机器人一条记录，不得缺失、重复或包含未知机器人。

每条机器人记录包含：

- `robot_id`：输入中的机器人标识。
- `path`：恰好 `H + 1` 个节点；`path[t]` 表示时刻 `t` 占据的节点。
- `actions`：零个或多个动作对象，包含整数 `time`、取值为 `pickup` 或 `dropoff` 的 `type`，以及输入中的 `order_id`。

不要输出自行声明的载荷、成本、分数或可行性字段；验证器不信任这些声明，输出模式也不允许额外字段。

## 硬约束

1. 每条路径必须从该机器人的指定起点开始。
2. 相邻时刻之间，机器人只能原地等待或沿输入图中的一条边移动。
3. 任意时刻，两台机器人不得占据同一节点。
4. 同一时间步内，两台机器人不得交换同一条边的两个端点。
5. 每个订单必须且只能取货一次、送货一次。
6. 取货必须发生在订单的取货节点，送货必须发生在送货节点。
7. 送货必须严格晚于取货，并由同一台机器人完成。
8. 同一机器人在同一时刻至多执行一个动作。
9. 机器人不得送出尚未携带的订单。
10. 初始载荷为零。取货增加订单重量，送货减少订单重量；载荷必须始终位于零和机器人载重上限之间。
11. 所有订单必须在时刻 `H` 之前或恰在 `H` 完成。
12. 输出中的节点、机器人标识和订单标识都必须来自输入实例。

不同机器人可以同时执行动作。原地等待不计入目标，但有限时域禁止无限等待。

## 目标与分数

验证器重新计算：

`D = 所有机器人在 t=1..H 范围内满足 path[t] != path[t-1] 的次数之和`。

需要最小化的原始指标为 `C = D + 1`。设基线原始指标为 `C_baseline`，单实例归一化分数为 `log2(C_baseline / C)`。数据集取各实例分数的算术平均值。非法方案得分为 `-1e18`。

总移动距离是唯一主目标。完工时间可以作为诊断指标，但不影响分数。

## 评测设计与隔离

本任务是离线批量 MAPD 变体：规划开始前全部订单均已知。它隔离评测联合分配、服务顺序、载重和无碰撞调度，而不模拟在线订单到达。选择总移动距离，是因为验证器可以根据完整路径确定性地独立重算该指标，并且在强制完成订单的条件下，移动量可作为车队能耗、磨损和通道占用的实用代理。引用的 Ma 等人工作提供 MAPD 动机，但研究的是不同的 lifelong online 吞吐量目标。

公开种子清单只包含公共种子和评测集规模。Frontier 不会把 `benchmark.yaml`、`data/`、`verification/`、`baseline/` 或 `reference/` 放入 agent 上下文；候选容器只接收自身源码和当前实例。这是运行时隔离，而不是对开源仓库的密码学隐藏。

## 实现规则

`scripts/init.py` 只能包含 `solve(instance)` 函数，所需导入必须写在函数内部。固定命令行封装由 Benchgen 添加。候选代码对确定输入必须保持确定性，不得访问网络、秘密信息、评估器输出或绝对路径，并须在配置的资源限制内完成。

Docker 是发布和正式评测的默认模式。`--local` 仅用于可信的本地开发。

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## 输入 Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "instance_id",
    "graph",
    "robots",
    "orders",
    "horizon"
  ],
  "properties": {
    "instance_id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 128
    },
    "graph": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "nodes",
        "edges"
      ],
      "properties": {
        "nodes": {
          "type": "array",
          "minItems": 2,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          }
        },
        "edges": {
          "type": "array",
          "items": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
              "type": "string",
              "minLength": 1,
              "maxLength": 128
            }
          }
        }
      }
    },
    "robots": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "start_node",
          "capacity"
        ],
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          },
          "start_node": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          },
          "capacity": {
            "type": "integer",
            "minimum": 1
          }
        }
      }
    },
    "orders": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "pickup_node",
          "dropoff_node",
          "weight"
        ],
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          },
          "pickup_node": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          },
          "dropoff_node": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          },
          "weight": {
            "type": "integer",
            "minimum": 1
          }
        }
      }
    },
    "horizon": {
      "type": "integer",
      "minimum": 1
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
    "robots"
  ],
  "properties": {
    "robots": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "robot_id",
          "path",
          "actions"
        ],
        "properties": {
          "robot_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128
          },
          "path": {
            "type": "array",
            "minItems": 2,
            "items": {
              "type": "string",
              "minLength": 1,
              "maxLength": 128
            }
          },
          "actions": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "time",
                "type",
                "order_id"
              ],
              "properties": {
                "time": {
                  "type": "integer",
                  "minimum": 0
                },
                "type": {
                  "type": "string",
                  "enum": [
                    "pickup",
                    "dropoff"
                  ]
                },
                "order_id": {
                  "type": "string",
                  "minLength": 1,
                  "maxLength": 128
                }
              }
            }
          }
        }
      }
    }
  }
}
```

## 约束与目标

输出必须满足上文全部硬约束。冻结验证器会独立检查可行性并重算
`verified_total_move_distance_plus_one`；优化目标是将这个严格为正的原始指标最小化。
有效实例使用相对基线的 `log2` 改进值，并取平均；无效方案得分为 `-1e18`。
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
