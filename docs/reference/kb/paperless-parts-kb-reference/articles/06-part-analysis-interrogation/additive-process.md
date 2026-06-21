---
title: "Additive process"
slug: additive-process
source: https://help.paperlessparts.com/s/article/additive-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Additive process

> Source: https://help.paperlessparts.com/s/article/additive-process  
> Topic: Part Analysis & Interrogation

Paperless Parts has created statistical models that can quickly estimate runtime and support volume for a number of popular 3D printers. Note, these numbers may not exactly match the runtime and support volume computed by your printer’s proprietary slicing tool; however, Paperless Parts estimates are typically computed in a fraction of the time required to completely slice a part.

Runtimes and support volumes are specific to a particular additive technology (e.g., FDM, SLA, SLS) and often to a particular printer make or model. Contact support to connect the best additive runtime model with your operation or to work with us to create a new model for your equipment.

To analyze a part for additive manufacturing, add this line to your pricing program:

additive = analyze_additive()

The `additive` object will contain the attributes described below.

| Attribute | Description | Metric units | US units |
| --- | --- | --- | --- |
| `runtime` | Estimated 3D print runtime. Based on a desktop FDM printer. Use it as a baseline to drive your printer estimation. Relative to the `orientation`. | hours | hours |
| `support_volume` | Estimated support volume. Based on a desktop FDM printer. Relative to the `orientation`. | mm^3 | in^3 |
| `orientation` | Suggested (or overridden) orientation; value will be one of ‘x’, ‘x_neg’, ‘y’, ‘y_neg’, ‘z’, ‘z_neg’. The suggested orientation is that which minimizes `aligned_height` followed by trying to minimize `runtime`    **NOTE**: Need to have a machine associated with the operation for intelligent orientation selection. The first operation in the router also must have an orientation selected.    **NOTE**: The default orientation is the positive Z dimension.    **NOTE**: When changing orientation, the part.size_x, part.size_y, and part.size_z values will be rotated assuming the respective values are originally set for an orientation of +Z. However, these values correspond to the optimal bounding box of 3D files, and **should not be used to drive orientation dependent pricing values**. Use `aligned_height` and `aligned_x`, `aligned_y`, and `aligned_z` to determine orientation based pricing values. | n/a | n/a |
| `material_volume` | Sum of part and support volume. Relative to the `orientation`. | mm^3 | in^3 |
| `does_part_fit` | If there is a machine with a build area associated with the operation, this will tell you if the part fits given the requested or calculated orientation; value will be `True` or `False` | n/a | n/a |
| `z_centroid` | The height of the center of mass of the part relative to the `orientation`. | mm | in |
| `shadow_volume` | The volume of shadow that exists when casting a light down onto the part relative to the `orientation`. Calculated as the projected downward area of all facets with any overhang multiplied by the height of that facet relative to the nearest intersection with the part itself or the ground. Useful for calculating support volume. | mm^3 | in^3 |
| `magic_number` | The estimated "shadow volume" of the part relative to the `orientation`. Calculated as the projected downward area of all facets with a greater than 45 degree overhang multiplied by the height of that facet relative to the nearest intersection with the part itself or the ground. Useful for calculating support volume. | mm^3 | in^3 |
| `xy_area` | The estimated area that is connected to the build plate relative to the `orientation`. Useful for calculating support raft. | mm^2 | in^2 |
| `aligned_x` | The X length of the part's axis aligned bounding box. | mm | in |
| `aligned_y` | The Y length of the part's axis aligned bounding box. | mm | in |
| `aligned_z` | The Z length of the part's axis aligned bounding box. | mm | in |
| `aligned_height` | The length of the axis aligned bounding box in the direction of the chosen `orientation`. | mm | in |

## Examples

This example suggests a height/layer based runtime model, perhaps more useful for SLA, SLS and other powder or resin based machines:

```
additive = analyze_additive()

#shop rates
machine_rate = var('Machine Rate', 100, '$/ hr', currency)
labor_rate = var('Labor Rate', 85, '$/ hr', currency)

#declare default setup and runtime
setup_time = var('setup_time', 0.25, 'setup time, hr', number)
runtime = var('runtime', 0, 'run time, hr', number, frozen=False)

#setup layer height and time per layer
layer_height = var('Layer Height in mm', .08, 'Height of each layer in mm', number)
layer_time = var('Layer Time, seconds', 10, 'Recoat time seconds', number)

#identify number of layers on part
part_layers = var('# of Layers',0, 'Total # of layers', number, frozen=False)
part_layers.update(ceil(part.aligned_height / layer_height))
part_layers.freeze()

#runtime update
runtime.update((part_layers * layer_time) / 3600)
runtime.freeze()

PRICE = setup_time * labor_rate + runtime * machine_rate * part.qty
DAYS = 0

```
