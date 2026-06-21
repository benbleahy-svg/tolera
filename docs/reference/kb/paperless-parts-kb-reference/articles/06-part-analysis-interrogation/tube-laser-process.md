---
title: "Tube laser process"
slug: tube-laser-process
source: https://help.paperlessparts.com/s/article/tube-laser-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Tube laser process

> Source: https://help.paperlessparts.com/s/article/tube-laser-process  
> Topic: Part Analysis & Interrogation

Paperless Parts has an interrogation module for tube laser processes. This module analyzes a 3D part file and extracts useful attributes for pricing including dimensions, cut length, pierce count, and cross section type. A diagram defining the dimensions of each compatible tube cross section can be found in our [Tube Laser Interrogation document](https://help.paperlessparts.com/article/212-tube-laser-interrogation).

You can customize the cut rate and pierce time of your equipment based on the material and thickness using custom tables. Take a look at our custom tables article on how to use these.

To analyze a part for a tube laser process, add this line to your pricing program:

tube_laser = analyze_tube_laser()

The `tube_laser` object will contain the attributes described below.

Tube Laser Attributes

| Attribute | Description | Metric units | US units |
| --- | --- | --- | --- |
| `stock_type` | Cross section of the tube, options include: `round`, `rectangular`, `rectangular_radiused`, `angle`, `u_channel`, and `incompatible` | n/a | n/a |
| `thickness` | Thickness of sheet metal part | mm | in |
| `length` | Length of the tube | mm | in |
| `width` | Width of the tube part (applicable for `rectangular`, `rectangular_radiused`, `angle`, and `u_channel` stock types) | mm | in |
| `height` | Height of the tube part (applicable for `rectangular`, `rectangular_radiused`, `angle`, and `u_channel` stock types) | mm | in |
| `diameter` | Diameter of the tube part (applicable for `round` stock type) | mm | in |
| `internal_radius` | Internal radius of the tube part (applicable for `rectangular_radiused`, `angle`, and `u_channel` stock types). For `uchannel` stock type, this is only set if both internal radii are equal. | mm | in |
| `outside_corner_radius` | Outside corner radius of the tube part (applicable for `angle` and `u_channel` stock types). For `u_channel` stock type, this is only set if both outside corner radii are equal. | mm | in |
| `leg_edge_radius` | Leg edge radius of the tube part (applicable for `angle` and `u_channel` stock types). This is only set if both leg edge radii are equal. | mm | in |
| `is_outside_corner_round` | Whether outside corner is round. Value will be `True` or `False` (applicable for `angle` and `u_channel` stock types). | n/a | n/a |
| `is_leg_edge_round` | Whether both leg edges are round. Value will be `True` or `False` (applicable for `angle` and `u_channel` stock types) | n/a | n/a |
| `leg_angle` | Angle (in degrees) between leg and base (applicable for `u_channel` stock type) | n/a | n/a |
| `total_cut_length` | Cut length across all cut out features you would mark | mm | in |
| `pierce_count` | Number of pierces of material required for a laser | n/a | n/a |
| `features` | P3LList copy of all tube laser features on the part | n/a | n/a |
| `feedback` | P3LList copy of all tube laser manufacturability feedback on the part | n/a | n/a |

## Basic Examples

This example suggests how to price your material operation for a tube laser process by length of the tube:

```
units_in()
tube_laser = analyze_tube_laser()
price_per_inch = var('Cost Per Inch', 1, '$/in', currency, frozen=True)
length = var('Tube Length', 0, 'in', number, frozen=False)

length.update(tube_laser.length)
length.freeze()

mat_cost = var('Material Unit Price ($)',230,'', currency, frozen=False)
mat_cost.update(price_per_inch * length)
mat_cost.freeze()
PRICE = part.qty * mat_cost
DAYS = part.mat_added_lead_time

```

This example suggests a simple way to price tube laser cutting:

```
units_in()
tube_laser = analyze_tube_laser()

cut_length = var('Cut Length (in)', 0, '', number, frozen=False)
cut_length.update(tube_laser.total_cut_length)
cut_length.freeze()

pierce_count = var('Pierce Count', 0, '', number, frozen=False)
pierce_count.update(tube_laser.pierce_count)
pierce_count.freeze()

cut_rate = var('Mat Cut Rate (in/min)', 20, '', number)
pierce_time = var('Mat Pierce Time (sec/pierce)', 2.5, '', number)

setup_time = var('setup_time', 10/60, 'Setup time (hr)', number, frozen=True)

runtime = var('runtime', 0, '', number, frozen=False)
runtime.update(cut_length / cut_rate / 60 + pierce_count * pierce_time / 3600)
runtime.freeze()
rate = var('Total Rate ($/hr)', 230, '', currency)

PRICE = runtime * part.qty * rate + setup_time * rate
DAYS = 0

```
