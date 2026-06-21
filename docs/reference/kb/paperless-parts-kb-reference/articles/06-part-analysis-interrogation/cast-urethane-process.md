---
title: "Cast urethane process"
slug: cast-urethane-process
source: https://help.paperlessparts.com/s/article/cast-urethane-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Cast urethane process

> Source: https://help.paperlessparts.com/s/article/cast-urethane-process  
> Topic: Part Analysis & Interrogation

Our pricing engine identifies features of parts that help you accurately price cast urethane processes.

## Mold Side Action Attributes

Part features like undercuts and certain types of side pockets make it difficult or impossible to remove a cast part from a two-piece mold. We identify the number of features requiring side action mold components.

## Mold Insert Attributes

Certain part features are best molded by using inserts, such as dowels or small machined metal pieces, to prevent fine mold features that are likely to wear out quickly and shorten the life of the mold. We detect features that should be molded with inserts and provide a count of various types of inserts.

**NOTE**:

- Inserts are required for hole or pocket-like features. Any hole or feature that propagates entirely through the part (“through” features) will require an insert. Some features that do not propagate entirely through (“blind” features) will require an insert if their aspect ratio (i.e., their effective cross-sectional area divided by their maximum depth) is below a certain threshold.
- A pin is used for a hole with uniform diameter and diameter less than 1/2”.
- A core is used for any hole with diameter greater than 1/2” or non-uniform diameter, as well as any pocket-type feature with an aspect ratio below the given threshold (7:1).
- A custom core is a core that requires more complicated machining or manufacturing to create. In particular, a custom core is an insert containing curved bottom transitions or complex profiling contours, and/or having more than 8 faces associated with it, and/or having a transition face like a fillet or chamfer going from its sides to its base.

To analyze a part for urethane casting, add this line to your pricing program:

casting = analyze_casting()

The `casting` object will contain the attributes described below.

| Attribute | Description | Units |
| --- | --- | --- |
| `pins` | Count of pins required for small through-holes | n/a |
| `cores` | Count of simple machined cores for pocket features and larger through-holes | n/a |
| `custom_cores` | Count of complex machined cores | n/a |
| `side_actions` | Count of required side actions | n/a |

## Example

This example suggests a simple way to cost for inserts, cores, custom cores, and side actions:

```
casting = analyze_casting()

insert_rate = var('Cost Per Insert', 5, 'Cost per insert', currency)
inserts = var('Inserts', 0, 'Count', number, frozen=False)
inserts.update(casting.pins + casting.cores + casting.custom_cores)
inserts.freeze()
insert_cost = inserts * insert_rate * part.qty

side_action_rate = var('Cost per side action', 50, 'Cost per side action', currency)
side_actions = var('Side Actions', 0, 'Count', number, frozen=False)
side_actions.update(casting.side_actions)
side_actions.freeze()
side_action_cost = side_actions * side_action_rate * part.qty

PRICE = insert_cost + side_action_cost
DAYS = 0

```
