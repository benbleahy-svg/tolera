---
title: "Lathe process"
slug: lathe-process
source: https://help.paperlessparts.com/s/article/lathe-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Lathe process

> Source: https://help.paperlessparts.com/s/article/lathe-process  
> Topic: Part Analysis & Interrogation

Paperless Parts has an interrogation module for lathe/turning operations. This module extracts useful information that influences pricing on turned parts. We will provide information such as a recommendation for cylindrical stock, setup count, and call out the need for live tooling.

We determine setup count assuming a typical lathe machine with a standard set of tools.

To analyze a part for a lathe/turning process, add this line to your pricing program:

lathe = analyze_lathe()

The `lathe` object will contain the attributes described below.

| Attribute | Description | Metric units | US units |
| --- | --- | --- | --- |
| `setup_count` | Total number of detected setups | n/a | n/a |
| `stock_radius` | Radius of recommended stock | mm | in |
| `stock_length` | Length of recommended stock | mm | in |
| `features` | P3LList copy of all lathe features | n/a | n/a |
| `feedback` | P3LList copy of all lathe feedback | n/a | n/a |

## Examples

This example suggests how to price your material based on the recommended stock from the interrogation:

```
 units_in() lathe = analyze_lathe() buffer = var('Buffer', 0.125, 'Stock buffer in inches', number) set_operation_name(part.material) stock_volume = 3.14159 * (lathe.stock_radius + buffer / 2)**2 * (lathe.stock_length + buffer) PRICE = stock_volume * part.mat_cost_per_volume * part.qty DAYS = part.mat_added_lead_time
```

This example shows how to price the lathe op based on recommended setups and a material removal rate:

```
 units_in() lathe = analyze_lathe()  shop_rate = var('Shop Rate', 75, '$ / hr', number) setup_time_per_setup = var('Setup time per setup', 0.5, 'hr', number) minimum_runtime = var('Min Runtime, hr', 0.08, 'Minimum turning runtime in hours', number)  buffer = var('Buffer', 0.125, 'Stock buffer in inches', number)  stock_volume = 3.14159 * (lathe.stock_radius + buffer / 2)**2 * (lathe.stock_length + buffer) volume_removal = stock_volume - part.volume  # establish base removal rate, and if volume removal is greater than certain threshold, use a higher value vol_cut_rate = var('Volume Cut Rate', 50, 'Cu. In./hr', number, frozen=False) if volume_removal > 15:   vol_cut_rate.update(70) vol_cut_rate.freeze()  runtime = var('runtime', 0, 'Runtime, hr', number, frozen=False) setup_time = var('setup_time', 0, 'Setup time, hr', number, frozen=False)  # now establish runtime based on max between minimum runtime and volume removal driven runtime runtime.update(max(minimum_runtime, volume_removal / vol_cut_rate)) runtime.freeze()  # now update setup time based on lathe detected setup count setup_time.update(lathe.setup_count * setup_time_per_setup) setup_time.freeze()  PRICE = (setup_time * shop_rate) + (runtime * part.qty * shop_rate) DAYS = 0
```
