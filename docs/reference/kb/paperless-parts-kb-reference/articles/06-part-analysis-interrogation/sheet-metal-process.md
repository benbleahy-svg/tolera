---
title: "Sheet metal process"
slug: sheet-metal-process
source: https://help.paperlessparts.com/s/article/sheet-metal-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Sheet metal process

> Source: https://help.paperlessparts.com/s/article/sheet-metal-process  
> Topic: Part Analysis & Interrogation

Paperless Parts supports manufacturing processes for sheet metal. From an uploaded CAD file, we will unbend the part and then determine parameters for a laser cutter or water jet machine, like the unfolded x and y dimensions, cut length, and number of pierces required through the material.

When cutting/fabricating the piece of metal prior to forming, these attributes assume a cutting process that can cut holes as small as the thickness of the material (by default). Contact support for information on customizing your interrogation.The pricing logic below supports laser/water jet/plasma cutter machines, punch machines, and punch-laser machines.We assume a secondary process (e.g., a drill press) will be used to produce counter-sinks, counter-bores, and small simple holes.You can customize the cut rate and pierce time of your equipment based on the material and thickness using custom tables. Take a look at our custom tables article on how to use these.

To analyze a part for a sheet metal process, add this line to your pricing program:

sheet_metal = analyze_sheet_metal()

The `sheet_metal` object will contain the attributes described below.

| Attribute | Description | Metric units | US units |
| --- | --- | --- | --- |
| `bend_count` | Count of bends | n/a | n/a |
| `thickness` | Thickness of sheet metal part | mm | in |
| `size_x` | X dimension of the unfolded sheet metal part | mm | in |
| `size_y` | Y dimension of the unfolded sheet metal part | mm | in |
| `total_cut_length` | Cut length across all cut out features you would cut with a laser/water jet/plasma cutter (excludes etchings) | mm | in |
| `total_air_move_length` | Sum of laser movement distances between cuts | mm | in |
| `pierce_count` | Number of pierces of material required for a laser/water jet/plasma cutter. **Note**: This only counts pierces for **internal features**. If you want to count a pierce for the external features as well, get the count of cutout features or add 1 to the pierce_count value. | n/a | n/a |
| `punch_single_hit_cut_length` | Cut length across all features that CAN be marked with a single hit of a punch tool. These contours are determined by their overall size and their simplicity (circles, squares, rectangles, slots, obround features) | mm | in |
| `punch_multi_hit_cut_length` | Cut length across all features that CANNOT be marked with a single hit of a punch tool, and thus need multiple hits. | mm | in |
| `punch_single_hit_setups` | Integer value of how many unique tools are required to accomplish all contours considered single-hit-punch features. | n/a | n/a |
| `punch_single_hit_count` | Total number of single hit punches performed across all single hit setups. | n/a | n/a |
| `counter_sink_setups` | The total number of distinct countersink setups for the hole part. A setup is defined with a major diameter, depth, and semi-angle. | n/a | n/a |
| `counter_sink_count` | The total number of countersinks across all countersink setups. | n/a | n/a |
| `counter_bore_setups` | The total number of distinct counterbore setups for the hole part. A setup is defined with a major diameter and a depth. | n/a | n/a |
| `counter_bore_count` | The total number of counterbores across all counterbore setups. | n/a | n/a |
| `simple_drilled_hole_setups` | The total number of distinct simple hole setups for the part. A setup is defined with a diameter. | n/a | n/a |
| `simple_drilled_hole_count` | The total number of simple drilled holes across all drilled hole setups. | n/a | n/a |
| `total_hole_setups` | The number of distinct hole setups across simple drilled holes, countersinks, and counterbores | n/a | n/a |
| `total_hole_count` | The total number of simple drilled holes, countersinks, and counterbores | n/a | n/a |
| `features` | P3LList copy of all sheet metal features on the part | n/a | n/a |
| `feedback` | P3LList copy of all sheet metal manufacturability feedback on the part |   |   |

## Basic Examples

This example suggests how to price your material operation for a sheet metal process:

```
units_in()
sheet_metal = analyze_sheet_metal()
set_operation_name(part.material)
buffer = var('Material Buffer', 0.125, 'Buffer in inches for raw material size', number)
PRICE = (sheet_metal.size_x + buffer) * (sheet_metal.size_y + buffer) * part.mat_cost_per_area * part.qty
DAYS = part.mat_added_lead_time
```

This example suggests a simple way to price the cutting/fabrication of part prior to forming bends:

```
sheet_metal = analyze_sheet_metal()

#shop rates
laser_rate = var('Laser Rate, $/hr', 85, '$ / hr', currency)
base_setup_time = var('Base Setup Time', 20, 'Base setup time for machine, min', number)
drilled_hole_setup_time = var('hole setup time', 10, 'time to setup unique drilled hole, min', number)
drilled_hole_runtime = var('hole runtime', 1, 'runtime for each hole to drill, min', number)

# NOTE: while all of these variables are derived from the ``flat`` module, we want to be able to override
# NOTE: these values when working with individual quote items, so we must declare them explicitly as variables
cut_length = var('cut length', 0, 'mm', number, frozen=False)
air_move_length = var('air move length', 0, 'mm', number, frozen=False)
pierce_count = var('pierce count', 0, 'number of times laser needs to pierce material', number, frozen=False)
hole_setups = var('hole setups', 0, 'number of unique hole setups', number, frozen=False)
count_holes = var('count drilled holes', 0, 'number of total drilled holes', number, frozen=False)
cut_length.update(sheet_metal.total_cut_length)
cut_length.freeze()
air_move_length.update(sheet_metal.total_air_move_length)
air_move_length.freeze()

# pierce count will be the number of loops minus one, as we wont count the outer loop of the part
pierce_count.update(sheet_metal.pierce_count)
pierce_count.freeze()
hole_setups.update(sheet_metal.total_hole_setups)
hole_setups.freeze()
count_holes.update(sheet_metal.total_hole_count)
count_holes.freeze()

# define fixed cut rates and pierce times (check out custom tables to have rates based on thickness and material)
cut_rate = var('cut rate', 2000, 'mm/minute', number)
pierce_time = var('pierce time', 2, 'pierce time in seconds', number)

# define laser movement speed for air moves
air_move_rate = var('air move rate', 5000, 'mm/minute', number)
setup_time = var('setup_time', 0, 'hr', number, frozen=False)
runtime = var('runtime', 0, 'hr', number, frozen=False)

# update runtime based on the cut rate and pierce times
# NOTE: units for the special variable named ``runtime`` and ``setup_time`` must be in HOURS
runtime.update(cut_length / cut_rate / 60 + air_move_length / air_move_rate / 60 + pierce_count * pierce_time / 3600 + count_holes * drilled_hole_runtime / 60)
runtime.freeze()

# update the setup time based on the ``base_setup_time`` and the number of unique hole setups
setup_time.update(base_setup_time / 60 + drilled_hole_setup_time / 60 * hole_setups)
setup_time.freeze()

PRICE = setup_time * laser_rate + runtime * laser_rate * part.qty
DAYS = 0
```

This example suggests a simple way to price your forming operation:

```
sm = analyze_sheet_metal()

# declare sheet metal rates
sheet_metal_rate = var('Sheet Metal Rate', 80, '$ / hr', currency)
setup_time_per_bend = var('Setup Time Per Bend (hr)', 0.25, 'hr', number)

# setup: 15 min / bend
run_time_per_bend = var('Run Time Per Bend (seconds)', 15, '
seconds per bend', number)

# runtime: 15 seconds / bend
setup_time = var('setup_time', 0, 'time / hr', number, frozen=False)
runtime = var('runtime', 0, 'time / hr', number, frozen=False)

#update setup time
setup_time.update(sm.bend_count * setup_time_per_bend)
setup_time.freeze()

#update runtime
runtime.update(sm.bend_count * run_time_per_bend / 3600)
runtime.freeze()

PRICE = sheet_metal_rate * setup_time + sheet_metal_rate * runtime * part.qty
DAYS = 0
```

Check out **Advanced Sheet Metal P3L** for more info on how to price sheet metal parts.
