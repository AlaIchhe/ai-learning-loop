---
description: workflow/ 层纯状态路由 — 图组装、节点编排、条件路由
paths:
  - "workflow/**"
---

# Workflow Layer — Pure Scheduling

`build_graph(opponent_compute_node, opponent_interact_node, presenter_compute_node, presenter_interact_node, referee_deliberate_node, checkpointer=None)`

```
START → start → opponent_compute → opponent_interact [interrupt]
  → presenter_compute → presenter_interact [interrupt]
  → referee_deliberate ──→ END (done)
              │                   │
              └── next_round ←────┘ (continue learning)
```

## Nodes
- **`start_node`**: `idle → opponent_computing`, `round = 1`, calls `validate_state_shape()`
- **`next_round_node`**: `round += 1`, clears 5 `_`-prefixed cache fields, preserves `_model_name`/`_model_base_url`
- **`_route_after_referee`**: `status == "done" → END`, `round >= max_rounds → END`, else `"next_round"`

## Key Rules
- No `interrupt_before` — human interaction uses dynamic `interrupt()` inside interact nodes
- `checkpointer` must be passed for `interrupt()` and `get_state()` to work
- `export_graph()` exports architecture diagram as PNG
