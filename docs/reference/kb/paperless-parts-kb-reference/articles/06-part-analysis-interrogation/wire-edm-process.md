---
title: "Wire EDM process"
slug: wire-edm-process
source: https://help.paperlessparts.com/s/article/wire-edm-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Wire EDM process

> Source: https://help.paperlessparts.com/s/article/wire-edm-process  
> Topic: Part Analysis & Interrogation

Paperless Parts has a module for Wire EDM based processes. From a 3D file, this module will extract things like cut length, average cut depth, and pierce count for you to use in your pricing formulas.

The module also recommends comprehensive manufacturability feedback in the partviewer. This module will contribute to the pricing variables only for features that can be manufactured with a standard wire-EDM machine. So for features like blind pockets, those areas of material removal will not contribute to pricing variables like cut length or cut depth. These features of a part that do not contribute to pricing variables will be highlighted in the partviewer.

To analyze a part for a wire EDM process, add this line to your pricing program:

wire = analyze_wire_edm()

The `wire` object will contain the attributes described below.

| Attribute | Description | Metric units | US units |
| --- | --- | --- | --- |
| `setup_count` | Total number of times required to refixture the part to machine all features that can be hit with a standard wire-EDM machine | n/a | n/a |
| `cut_length` | The aggregate cut length across all setups and cuttable features (for features that are cut on an angle, we take the average length between the top and bottom contours) | mm | in |
| `pierce_count` | Number of times a drill will have to be used to create a feed hole for the wire | n/a | n/a |
| `average_cut_depth` | The cut-length-weighted average depth of cut for the wire EDM machine across all setups (for features cut at an angle, we take the average cut depth across the entire cut face) | mm | in |

## Example

This example uses a very straightforward cut rate function based on the depth of the cut:

```
 units_in() wire = analyze_wire_edm()  min_cut_rate = 0.007 cut_rate_slope = 0 - 0.009 cut_rate_intercept = 0.05  cut_rate_calculated = cut_rate_slope * wire.average_cut_depth + cut_rate_intercept if cut_rate_calculated < min_cut_rate:   cut_rate_use = min_cut_rate else:   cut_rate_use = cut_rate_calculated  cut_rate = var('Cut Rate', 0, 'in/min', number, frozen=False) cut_rate.update(cut_rate_use) cut_rate.freeze()  setup_time_per_setup = var('Base Setup Time per setup', 60.0, 'minutes', number) total_setup_time = var('setup_time', 0, 'total setup time, hours', number, frozen=False) total_setup_time.update(wire.setup_count * setup_time_per_setup / 60.0) total_setup_time.freeze()  runtime_per_drilled_hole = var('Runtime Per Drilled Hole', 2.5, 'minutes', number) total_drilled_runtime = wire.pierce_count * runtime_per_drilled_hole / 60.0  runtime = var('runtime', 0, 'runtime in hours', number, frozen=False) runtime.update(total_drilled_runtime + wire.cut_length / cut_rate / 60.0) runtime.freeze()  machine_rate = var('Machine Rate', 95.0, '$/hr', currency) setup_rate = var('Setup Rate', 95.0, '$/hr', currency)  PRICE = part.qty * runtime * machine_rate + total_setup_time * setup_rate DAYS = 0
```
