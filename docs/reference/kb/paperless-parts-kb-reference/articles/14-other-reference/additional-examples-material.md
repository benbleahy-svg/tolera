---
title: "Additional examples, material"
slug: additional-examples-material
source: https://help.paperlessparts.com/s/article/additional-examples-material
topic: "Other / Reference"
captured: 2026-06-19
---

# Additional examples, material

> Source: https://help.paperlessparts.com/s/article/additional-examples-material  
> Topic: Other / Reference

# Material Pricing

The following examples should help you implement an operation that replicates and enhances the way your shop prices materials.

We recommend you grasp the [basics of P3L](https://help.paperlessparts.com/article/42-p3l-language-features) and [the part object](https://help.paperlessparts.com/article/43-the-part-object) before diving in to these examples.

### Basic Material Pricing

A simple way to price material is on a price-per-pound basis. Paperless Parts converts your specified material cost per pound into cost per unit volume, so it can be easily multiplied by part volume. This is the most basic way to price material, and fits best for quoting small quantities.

```
units_in()
buffer = var('Buffer', 0.25, 'Stock buffer in inches', number)
bbox = (part.size_x + buffer) * (part.size_y + buffer) * (part.size_z + buffer)
set_operation_name(part.material)
PRICE = bbox * part.mat_cost_per_volume * part.qty
DAYS = part.mat_added_lead_time

```

### ERP-Style Material Pricing

The following examples mirror the way ERP systems like JobBoss and E2 price materials for different processes. Our interrogations supplement the typical ERP workflow by giving the operation the context of the part geometry, allowing us to give values for things like parts per sheet and parts per bar.

#### Material By Bar Rectangular

```
# This prices material based on a parts per bar model, where you enter in the price per bar at quote time.
# Assumes a rectangular cross section bar.

units_in()

if part.material:
    set_operation_name(part.material)

price_per_bar = var('Price Per Bar', 0, 'Input Price for Below Bar Size', currency)
bar_length = var('Bar Length, in', 96, '', number)

part_length = var('Part Length, in', 0, '', number, frozen=False)
part_length.update(max(part.size_x, part.size_y, part.size_z))
part_length.freeze()

cutoff = var('Cutoff, in', 0.125, '', number)
facing = var('Facing, in', 0, '', number)

bar_end = var('Bar End, in', 0, 'Length of bar allocated for holding', number)

# required bars
parts_per_bar = var('Parts Per Bar', 0, '', number, frozen=False)
parts_per_bar.update(floor((bar_length - bar_end) / (part_length + cutoff + facing)))
parts_per_bar.freeze()

if parts_per_bar > 0:
    bars = ceil(part.qty / parts_per_bar)
else:
    bars = 1

PRICE = price_per_bar * bars

# part.mat_added_lead_time is specified in process material setup, defaults to 0
DAYS = part.mat_added_lead_time

```

#### Material By Bar Cylindrical

```
# This prices material based on a parts per bar model, where you enter in the price per bar at quote time.
# Assumes a cylindrical bar cross section. We call our lathe interrogation to establish the lathe axis, which then
# allows us to determine the cylindrical stock radius and stock length.

units_in()
lathe = analyze_lathe()

if part.material:
    set_operation_name(part.material)

price_per_bar = var('Price Per Bar', 0, 'Input Price for Below Bar Size', currency)
bar_length = var('Bar Length, in', 96, '', number)

part_length = var('Part Length, in', 0, '', number, frozen=False)
part_length.update(lathe.stock_length)
part_length.freeze()

cutoff = var('Cutoff, in', 0.125, '', number)
facing = var('Facing, in', 0, '', number)

bar_end = var('Bar End, in', 0, 'Length of bar allocated for holding', number)

# required bars
parts_per_bar = var('Parts Per Bar', 0, '', number, frozen=False)
parts_per_bar.update(floor((bar_length - bar_end) / (part_length + cutoff + facing)))
parts_per_bar.freeze()

if parts_per_bar > 0:
    bars = ceil(part.qty / parts_per_bar)
else:
    bars = 1

PRICE = price_per_bar * bars

# part.mat_added_lead_time is specified in process material setup, defaults to 0
DAYS = part.mat_added_lead_time

```

#### Material By Sheet

```
# Prices material on a per sheet basis. Based on a parts greatest two dimensions and an
# inputted sheet width and sheet length, this operation calculates how many sheets you need
# to fulfill a make quantity. This calculated value can be overridden at quote time if needed
# The price is then generated based on an inputted price per sheet.
# We call analyze_sheet_metal to get the unfolded dimensions of the part

units_in()
sm = analyze_sheet_metal()

if part.material:
    set_operation_name(part.material)

part_thickness = var('Part Thickness, in', 0, '', number, frozen=False)
part_thickness.update(sm.thickness)
part_thickness.freeze()

price_per_sheet = var('Price Per Sheet', 0, '', currency)
sheet_length = var('Sheet Length, in', 96, 'Longer dimension of sheet in inches', number)
sheet_width = var('Sheet Width, in', 48, 'Shorter dimension of sheet in inches', number)

part_length = var('Part Length, in', 0, 'Longest dimension of part', number, frozen=False)
part_length.update(max(sm.size_x, sm.size_y))
part_length.freeze()

part_width = var('Part Width, in', 0, 'Width of part', number, frozen=False)
part_width.update(min(sm.size_x, sm.size_y))
part_width.freeze()

material_buffer = var('Material Buffer, in', 0.125, 'Buffer in each dimension around part on sheet', number)

length = max(sheet_length, sheet_width)
width = min(sheet_length, sheet_width)

parts_per_sheet = var('Parts Per Sheet', 0, '', number, frozen=False)
if part_length > length or part_width > width:
    parts_per_sheet.update(0)
else:
    buffered_length = part_length + material_buffer
    buffered_width = part_width + material_buffer
    length_fit_count = floor(length / buffered_length)
    width_fit_count = floor(width / buffered_width)
    parts_per_sheet.update(width_fit_count * length_fit_count)
parts_per_sheet.freeze()

if parts_per_sheet > 0:
    sheets = ceil(part.qty / parts_per_sheet)
else:
    sheets = 1

PRICE = price_per_sheet * sheets

# part.mat_added_lead_time is specified in process material setup, defaults to 0
DAYS = part.mat_added_lead_time

```

### Additional Material Operations

#### Material Prep

```
# Assumes one cut for every part in make quantity. Builds on the standard
# work center costing logic.

units_in()

setup_time = var('setup_time', 0, 'Setup Time in hours', number)
runtime = var('runtime', 0.0028, 'Runtime per material prep cut in hours (10 seconds)', number)

setup_labor_rate = var('Setup Labor Rate', 0, 'Labor cost per hour to setup workcenter', currency)
run_labor_rate = var('Run Labor Rate', 0, 'Labor cost per hour to attend workcenter machine', currency)
machine_rate = var('Machine Rate', 0, 'Cost per hour to keep workcenter machine occupied', currency)
efficiency = var('Efficiency', 100, 'Percentage of real time the workcenter is running with regards to runtime', number)
percent_attended = var('Percent Attended', 100, 'Percentage of time workcenter must be attended', number)
crew = var('Crew', 1, 'Number of people assigned to attend workcenter', number)

total_cycle_time = part.qty * runtime
total_machine_occupied_time = total_cycle_time / efficiency * 100
total_attended_time = total_machine_occupied_time * percent_attended / 100

setup_cost = setup_time * setup_labor_rate
workcenter_usage_cost = total_machine_occupied_time * machine_rate
run_labor_cost = total_attended_time * run_labor_rate * crew

PRICE = setup_cost + workcenter_usage_cost + run_labor_cost
DAYS = 0

```

#### Material Markup

```
# This applies a markup to material price by extracting it from the pricing dict.
# You can set your material markup with a default value, and modify it at quote time.

markup = var('Markup Percentage', 0, 'Percent markup on material cost', number)
material_cost = get_price_value('--material--')
if part.material:
    set_operation_name('{} Markup: {}%'.format(part.material, markup))

PRICE = material_cost * markup / 100
DAYS = 0

```
