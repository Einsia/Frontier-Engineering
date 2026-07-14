# Task: Warehouse Robot Routing

Implement `solve(instance)` in `scripts/init.py`.

## Input

The input object contains:

- `instance_id`: a non-empty identifier.
- `graph.nodes`: all valid node identifiers.
- `graph.edges`: undirected traversable edges, each represented by two node identifiers.
- `robots`: objects with `id`, `start_node`, and positive integer `capacity`.
- `orders`: objects with `id`, `pickup_node`, `dropoff_node`, and positive integer `weight`.
- `horizon`: the final discrete time `H`.

## Output

Return an object with exactly one top-level field, `robots`. Its array must contain exactly one entry for every input robot and no unknown or duplicate robot.

Each robot entry contains:

- `robot_id`: the input robot identifier.
- `path`: exactly `H + 1` nodes. `path[t]` is the occupied node at time `t`.
- `actions`: zero or more objects with integer `time`, `type` equal to `pickup` or `dropoff`, and an input `order_id`.

Do not include claimed loads, costs, scores, or feasibility flags; the verifier ignores such claims and the output schema rejects extra fields.

## Hard Constraints

1. Every path starts at its robot's specified start node.
2. Between adjacent times, a robot either waits or traverses one input edge.
3. No two robots occupy the same node at the same time.
4. Two robots may not swap endpoints of one edge during the same time step.
5. Every order is picked up exactly once and dropped off exactly once.
6. Pickup occurs at the order's pickup node. Dropoff occurs at its dropoff node.
7. Dropoff is strictly later than pickup and is performed by the same robot.
8. A robot may perform at most one action at any time.
9. A robot cannot drop an order it is not carrying.
10. Loads start at zero. Pickup adds the order weight and dropoff subtracts it. Load must remain between zero and robot capacity.
11. Every order must be delivered no later than time `H`.
12. Every node, robot identifier, and order identifier in the output must be known to the instance.

Actions by different robots may occur simultaneously. Waiting is free in the objective but the finite horizon prevents unbounded schedules.

## Objective and Score

The verifier recomputes

`D = sum over robots and t=1..H of [path[t] != path[t-1]]`.

The minimized raw metric is `C = D + 1`. With baseline raw metric `C_baseline`, the normalized instance score is `log2(C_baseline / C)`. Scores are averaged across instances. Invalid solutions receive `-1e18`.

Distance is the only primary objective. Completion time may be reported as a diagnostic but does not change the score.

## Implementation Rules

`scripts/init.py` may contain only the `solve(instance)` function, with imports placed inside that function. Benchgen adds the fixed command-line wrapper. Candidate code must be deterministic for deterministic inputs, must not access the network, secrets, evaluator outputs, or absolute paths, and must finish within the configured resource limits.

Docker is the default mode for publishing and formal evaluation. The `--local` option is only for trusted local development.

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## Input Schema

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

## Output Schema

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

## Constraints and Objective

The output must satisfy every hard constraint described above. The frozen verifier independently
checks feasibility and recomputes `verified_total_move_distance_plus_one`. The objective is to minimize
that strictly positive raw metric. Valid cases use `log2` baseline improvement and are aggregated
with the mean; invalid solutions receive `-1e18`.
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
