# Task: Dependency-Aware Cybersecurity Patch Scheduling

Implement `solve(instance)` in `scripts/init.py`. The function must return a JSON-compatible object with exactly one field, `schedule`.

A schedule has the form `{'schedule': [{'patch_id': 'P000', 'start_slot': 0}, ...]}`. Each entry must contain exactly `patch_id` and `start_slot`. Patch identifiers must exist in the instance, start slots must be non-negative integers, and a patch may appear at most once. Omitting a patch means it is not applied.

## Scheduling semantics

A selected patch occupies the half-open interval `[start_slot, start_slot + duration)`. Execution is non-preemptive, and the completion slot is derived from the instance.

Every submitted schedule must satisfy all of the following:

- Every patch completes no later than `horizon`.
- Selecting a patch selects every direct and transitive prerequisite.
- Every direct prerequisite completes no later than the dependent patch starts.
- A patch interval is wholly contained in at least one maintenance window of every affected asset and every service listed in its service demands.
- Patches affecting the same asset cannot overlap when that asset has `exclusive_change` set to true.
- In every slot, aggregate demand for each renewable resource is no greater than its slot capacity.
- In every slot, aggregate downtime demand for each service is no greater than its slot capacity.
- Total downtime units for each service are no greater than its maintenance budget.

All durations, relationships, demands, and costs are authoritative instance data. Candidate-supplied completion times, costs, or feasibility claims are not accepted.

## Objective

Minimize total expected monetary loss in microunits.

For each vulnerability, remediation occurs at the earliest completion of any selected covering patch. If no covering patch completes, remediation time is the horizon. Security loss uses all exploit probabilities in slots before remediation. The vulnerability impact is first adjusted by `criticality_ppm`, and the cumulative exploit probability is computed by repeatedly multiplying the probability of no exploit using the instance scale of 1,000,000.

Business loss is the sum of `downtime_units * loss_microunits_by_slot[t]` over every selected patch, demanded service, and occupied slot. Rollback loss is the rounded value of `rollback_probability_ppm * rollback_impact_microunits / 1,000,000` for each selected patch.

The verifier recomputes feasibility and the raw objective exclusively from the instance and schedule. Lower raw values are better. Framework-owned normalization is `log2(baseline_raw / candidate_raw)`; it is not part of `solve` or `evaluate_solution`.

## Determinism and isolation

`solve` must be deterministic for a given instance. It must not read files, use the network, inspect environment variables or secrets, use evaluator output, or depend on hidden seed values. Keep every import required by `scripts/init.py` inside `solve`.

The supplied starter is a feasible self-contained baseline. You may replace its internal heuristic while preserving the required function signature and output schema.

<!-- BENCHGEN-PUBLIC-CONTRACT-START -->
## Input Schema

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

## Output Schema

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

## Constraints and Objective

The output must satisfy every hard constraint described above. The frozen verifier independently
checks feasibility and recomputes `verifier_recomputed_total_expected_monetary_loss_microunits`. The objective is to minimize
that strictly positive raw metric. Valid cases use `log2` baseline improvement and are aggregated
with the mean; invalid solutions receive `-1e18`.

The problem setting is `offline_batch`. Objective rationale: Expected monetary loss is appropriate because patching is not valuable merely for maximizing patch count or minimizing completion time. It prices the security exposure retained by delaying or omitting patches while also charging for the business disruption and rollback exposure caused by applying them. Expressing all three components in a common monetary unit produces a continuous, auditable tradeoff and keeps feasibility rules separate from preferences. The raw objective is strictly lower-is-better and can be kept positive through instance construction, making it suitable for framework-owned log2_baseline_ratio normalization.
Literature alignment: NIST SP 800-40 Rev. 4 frames enterprise patching as risk-based preventive maintenance that must be planned alongside operational constraints. CISA BOD 22-01 provides a concrete basis for prioritizing vulnerabilities with evidence of active exploitation and for modeling remediation deadlines. This benchmark turns those planning principles into a deterministic offline optimization problem; its synthetic monetary loss, rollback, resource, and downtime parameters are benchmark abstractions rather than values claimed by either source. It differs from classical makespan scheduling by allowing economically rational patch omission and by jointly enforcing dependency closure, maintenance calendars, renewable resources, and service downtime limits.
<!-- BENCHGEN-PUBLIC-CONTRACT-END -->
