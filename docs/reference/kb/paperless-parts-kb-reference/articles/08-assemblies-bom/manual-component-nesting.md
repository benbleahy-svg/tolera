---
title: "Manual component nesting"
slug: manual-component-nesting
source: https://help.paperlessparts.com/s/article/manual-component-nesting
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Manual component nesting

> Source: https://help.paperlessparts.com/s/article/manual-component-nesting  
> Topic: Assemblies & BOM

Paperless Parts has a nesting module for parts analyzed by our sheet metal interrogation. This module takes a flattened geometry and user-specified inputs to generate a nest for a single component on a specified sheet size.

**Note:**this nesting module is separate from our[Multi-component sheet metal nesting](https://help.paperlessparts.com/article/401-multi-component-sheet-metal-nesting)module.

In order to access the module from your material operation, add `sheet_metal = analyze_sheet_metal()` to your material pricing program in order to ensure it will be analyzed using our sheet metal interrogation. Now, when you expand this material operation in your quote, this interface will appear:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/60f0a3616ffe270af2a8f594/file-9JStc2z9Q8.png)

You can request a nest for each quantity break with the different parameters described above. After a nesting request is complete, a result will be returned that gives you all the information you need to establish pricing:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/60f0a348b55c2b04bf6d4d92/file-2UrEVimHZe.png)

You can "zoom-in" on these results by clicking them, to get a more detailed image of the nesting output.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/60f0a31a766e8844fc346fff/file-PYdtR1wH0o.png)

Here is a quick video demo of how the nesting module works:

Contact support or your account manager for more information on how we can help set this up for you in your pricing formulas. For those that wish to implement the code themselves, here is the documentation:

To access results from the nesting module from within P3L, add this line to your operation pricing program:

nest = manual_nest()

The `nest` object will contain one attribute: `sheets` which returns a [P3L List](https://help.paperlessparts.com/article/215-p3l-lists) of sheet objects. Each sheet object has the same attributes. The `nest` object will be `None` if no manual nest request has been made in the user interface. Adding another line, for example, allows you to access one of the sheet objects:

`sheet = nest.sheets[0]`

The `sheet` object will contain the attributes described below.

Sheet Attributes

| Attribute | Description | Metric units | US units |
| --- | --- | --- | --- |
| `count` | Number of times this sheet is used | n/a | n/a |
| `parts_per_sheet` | Number of parts that fit on this sheet | n/a | n/a |
| `utilized_area` | Area used by parts | mm2 | in2 |
| `yield_pct` | Utilized area divided by total area | n/a | n/a |
| `scrap_area` | Area not used by parts and not counted as drop | mm2 | in2 |
| `scrap_pct` | Scrap area divided by total area | n/a | n/a |
| `drop_area` | Area that can be salvaged from the sheet | mm2 | in2 |
| `drop_pct` | Drop area divided by total area | n/a | n/a |
| `length` | Length of the sheet | mm | in |
| `width` | Width of the sheet | mm | in |
| `thickness` | Thickness of the sheet | mm | in |
| `part_grain_direction` | Specified grain direction (string) | n/a | n/a |
| `drop_threshold` | Specified drop threshold | mm | in |
| `edge_buffer` | Specified edge buffer | mm | in |
| `is_common_line_cutting_enabled` | Specified common line cutting setting | n/a | n/a |
| `kerf_width` | Specified kerf width | mm | in |
| `part_buffer` | Specified part buffer | mm | in |

## Examples

This example suggests how to price your sheet using nesting results (but also standard backup for quantities that do not have nesting results) :

```
units_in()
sm = analyze_sheet_metal()

part_thickness = var('Part Thickness, in', 0, '', number, frozen=False)
part_thickness.update(round(sm.thickness or part.size_z, 5))
part_thickness.freeze()

part_length = var('Part Length, in', 0, 'Longest dimension of part', number, frozen=False)
part_length.update(round(max(sm.size_x, sm.size_y) or max(part.size_x, part.size_y), 5))
part_length.freeze()

part_width = var('Part Width, in', 0, 'Width of part', number, frozen=False)
part_width.update(round(min(sm.size_x, sm.size_y) or min(part.size_x, part.size_y), 5))
part_width.freeze()

edge_buffer = var(
    'Edge Buffer, in', 0.125, 'Distance from edge of sheet to parts', number, frozen=False
)
part_buffer = var(
    'Part Buffer, in', 0.0625, 'Buffer distance around flattened part in X-Y', number, frozen=False
)

is_using_manual_nest = drop_down_var(
    'Is Using Manual Nest?', 'No', create_list('Yes'), '', string, quantity_specific=True, frozen=False
)
nest = manual_nest()
first_sheet = None
last_sheet = None
if nest and nest.sheets:
    is_using_manual_nest.select_option('Yes')
    first_sheet = nest.sheets[0]
    last_sheet = nest.sheets[1] if len(nest.sheets) > 1 else None
else:
    is_using_manual_nest.select_default()

if is_using_manual_nest.value == 'Yes' and first_sheet:
    edge_buffer.update(first_sheet.edge_buffer)
    part_buffer.update(first_sheet.part_buffer)
edge_buffer.freeze()
part_buffer.freeze()

sheet_length = var('Sheet Length, in', 96, '', number, quantity_specific=True, frozen=False)
sheet_width = var('Sheet Width, in', 48, '', number, quantity_specific=True, frozen=False)
sheet_thickness = var('Sheet Thickness, in', 0, '', number, quantity_specific=True, frozen=False)
if is_using_manual_nest.value == 'Yes' and first_sheet:
    sheet_length.update(first_sheet.length)
    sheet_width.update(first_sheet.width)
    sheet_thickness.update(first_sheet.thickness)
sheet_length.freeze()
sheet_width.freeze()
sheet_thickness.freeze()

buffered_part_length = part_length + part_buffer
buffered_part_width = part_width + part_buffer

# usable dimensions exclude edge buffer on both sides
# add one part buffer so we do not double count part buffer, as that is only between parts
usable_sheet_length = max(sheet_length, sheet_width) - 2 * edge_buffer + part_buffer
usable_sheet_width = min(sheet_length, sheet_width) - 2 * edge_buffer + part_buffer

parts_per_sheet = var('Parts Per Sheet', 0, '', number, frozen=False, quantity_specific=True)
if is_using_manual_nest.value == 'Yes' and first_sheet:
    parts_per_sheet.update(first_sheet.parts_per_sheet)
elif part_length > usable_sheet_length or part_width > usable_sheet_width:
    parts_per_sheet.update(0)
else:
    length_fit_count = floor(usable_sheet_length / buffered_part_length)
    width_fit_count = floor(usable_sheet_width / buffered_part_width)
    parts_per_sheet.update(width_fit_count * length_fit_count)
parts_per_sheet.freeze()

number_of_sheets = var('# of Sheets', 1, '', number, frozen=False, quantity_specific=True)
if is_using_manual_nest.value == 'Yes' and nest and nest.sheets:
    temp_number_of_sheets = 0
    for sheet in iterate(nest.sheets):
        temp_number_of_sheets += sheet.count
    number_of_sheets.update(temp_number_of_sheets)
elif parts_per_sheet > 0:
    number_of_sheets.update(ceil(part.qty / parts_per_sheet))
number_of_sheets.freeze()

# PLACEHOLDER, HERE IS WHERE YOU INCLUDE LOGIC FOR SHEET COST
# could query to a custom table, use square inch pricing, or use per pound pricing
sheet_cost = var('Sheet Cost', 0, '', currency, frozen=False, quantity_specific=True)
sheet_cost.freeze()

material_cost = 0
sheet_toggle = drop_down_var(
    'Price Calculation', 'Net Sheet Used', create_list('Total Sheets Required'), '', string
)
if sheet_toggle.value == 'Total Sheets Required':
    material_cost = sheet_cost * number_of_sheets
elif sheet_toggle.value == 'Net Sheet Used':
    if is_using_manual_nest.value == 'Yes' and nest and nest.sheets:
        for sheet in iterate(nest.sheets):
            used_pct = sheet.yield_pct + sheet.scrap_pct
            material_cost += sheet_cost * sheet.count * used_pct
    elif parts_per_sheet > 0:
        material_cost = (1 / parts_per_sheet) * sheet_cost * part.qty

PRICE = material_cost
DAYS = 0

```

This example suggests a way to reference a custom table ('sheet_lookup' in this example) containing sheet pricing, and uses your nesting results to calculate sheet costs. This also will give the user a recommended sheet size from a table of sheets based on the unfolded part geometry. This is the operation used for this nesting demo video:

```
units_in()
sm = analyze_sheet_metal()

part_thickness = var('Part Thickness, in', 0, '', number, frozen=False)
part_thickness.update(round(sm.thickness or part.size_z, 5))
part_thickness.freeze()

part_length = var('Part Length, in', 0, 'Longest dimension of part', number, frozen=False)
part_length.update(round(max(sm.size_x, sm.size_y) or max(part.size_x, part.size_y), 5))
part_length.freeze()

part_width = var('Part Width, in', 0, 'Width of part', number, frozen=False)
part_width.update(round(min(sm.size_x, sm.size_y) or min(part.size_x, part.size_y), 5))
part_width.freeze()

edge_buffer = var(
    'Edge Buffer, in', 0.125, 'Distance from edge of sheet to parts', number, frozen=False
)
part_buffer = var(
    'Part Buffer, in', 0.0625, 'Buffer distance around flattened part in X-Y', number, frozen=False
)
thickness_tolerance = var(
    'Thickness Tol, in', 0.01, '+/- buffer of model thickness used to find potential sheets', number
)

is_using_manual_nest = drop_down_var(
    'Is Using Manual Nest?', 'No', create_list('Yes'), '', string, quantity_specific=True, frozen=False
)
nest = manual_nest()
first_sheet = None
last_sheet = None
if nest and nest.sheets:
    is_using_manual_nest.select_option('Yes')
    first_sheet = nest.sheets[0]
    last_sheet = nest.sheets[1] if len(nest.sheets) > 1 else None
else:
    is_using_manual_nest.select_default()

if is_using_manual_nest.value == 'Yes' and first_sheet:
    edge_buffer.update(first_sheet.edge_buffer)
    part_buffer.update(first_sheet.part_buffer)
edge_buffer.freeze()
part_buffer.freeze()

# do a table lookup strictly for reference to type in sheet nesting values
row = table_var(
    'Sheet Search',
    'reference table lookup to find applicable sheets for nesting',
    'sheet_lookup',
    create_filter(
        filter('material', '=', part.global_material),
        filter(
            'thickness',
            'range',
            create_range(
                part_thickness - thickness_tolerance, part_thickness + thickness_tolerance
            ),
        ),
        filter('length', '>=', part_length + edge_buffer),
        filter('width', '>=', part_width + edge_buffer),
    ),
    create_order_by('thickness', '-length', '-width', 'sheet_cost'),
    'display',
)

# recommend a sheet size for each quantity break given a back of the napkin nesting calculation
rows = table_lookup(
    'sheet_lookup',
    create_filter(
        filter('material', '=', part.global_material),
        filter(
            'thickness',
            'range',
            create_range(
                part_thickness - thickness_tolerance, part_thickness + thickness_tolerance
            ),
        ),
        filter('length', '>=', part_length + edge_buffer),
        filter('width', '>=', part_width + edge_buffer),
    ),
    create_order_by('thickness', '-length', '-width', 'sheet_cost'),
)

# collect unique thicknesses from returned rows and choose the smallest thickness to restrict our search
search_thickness = drop_down_var('Search Thickness, in', 0, create_list(), '', number, frozen=False)
if rows:
    # collect unique diameters
    unique_thicknesses = create_list()
    for row in iterate(rows):
        if row.thickness not in unique_thicknesses:
            unique_thicknesses.append(row.thickness)
    # select smallest thickness, should be first entry as rows are already sorted
    search_thickness.clear_options()
    search_thickness.update_options(unique_thicknesses)
    search_thickness.select_option_or_default(min(unique_thicknesses))
else:
    search_thickness.select_option(part_thickness, force=True)

buffered_part_length = part_length + part_buffer
buffered_part_width = part_width + part_buffer

# for each one of the rows that match the search thickness, estimate a parts per sheet using flat
# x-y dimensions and the buffers.
# select the cheapest sheet that can alone satisfy the quantity based on PPS estimate
# if no sheets found that can individually satisfy quantity, select the largest, cheapest sheet by cross sectional area
min_thickness_rows = rows.filter(lambda x: x.thickness == search_thickness.value)
use_row = None
if min_thickness_rows:
    # select best sheet size based on if PPS estimate can satisfy entire quantity
    min_thickness_rows.sort(lambda x: x.sheet_cost)
    use_row = None
    for sheet_option in iterate(min_thickness_rows):
        # usable dimensions exclude edge buffer on both sides
        # add one part buffer so we do not double count part buffer, as that is only between parts
        usable_length = max(sheet_option.length, sheet_option.width) - 2 * edge_buffer + part_buffer
        usable_width = min(sheet_option.length, sheet_option.width) - 2 * edge_buffer + part_buffer

        length_fit_count = floor(usable_length / buffered_part_length)
        width_fit_count = floor(usable_width / buffered_part_width)
        parts_per_sheet = width_fit_count * length_fit_count

        if parts_per_sheet > part.qty:
            use_row = sheet_option
            break

    if not use_row:
        # select the largest and cheapest sheet
        use_row = min_thickness_rows.sort(
            lambda x: create_multi_sort(-x.length * x.width, x.sheet_cost)
        )[0]

# show recommended values
recommended_length = var('Recommended Length, in', 120, '', number, frozen=False, quantity_specific=True)
recommended_width = var('Recommended Width, in', 60, '', number, frozen=False, quantity_specific=True)
recommended_thickness = var('Recommended Thickness, in', 0, '', number, frozen=False, quantity_specific=True)
if use_row:
    recommended_length.update(use_row.length)
    recommended_width.update(use_row.width)
    recommended_thickness.update(use_row.thickness)
else:
    recommended_thickness.update(part_thickness)
recommended_length.freeze()
recommended_width.freeze()
recommended_thickness.freeze()

sheet_length = var('Sheet Length, in', 120, '', number, quantity_specific=True, frozen=False)
sheet_width = var('Sheet Width, in', 60, '', number, quantity_specific=True, frozen=False)
sheet_thickness = var('Sheet Thickness, in', 0, '', number, quantity_specific=True, frozen=False)
if is_using_manual_nest.value == 'Yes' and first_sheet:
    sheet_length.update(first_sheet.length)
    sheet_width.update(first_sheet.width)
    sheet_thickness.update(first_sheet.thickness)
elif row:
    sheet_length.update(recommended_length)
    sheet_width.update(recommended_width)
    sheet_thickness.update(recommended_thickness)
sheet_length.freeze()
sheet_width.freeze()
sheet_thickness.freeze()

buffered_part_length = part_length + part_buffer
buffered_part_width = part_width + part_buffer

# usable dimensions exclude edge buffer on both sides
# add one part buffer so we do not double count part buffer, as that is only between parts
usable_sheet_length = max(sheet_length, sheet_width) - 2 * edge_buffer + part_buffer
usable_sheet_width = min(sheet_length, sheet_width) - 2 * edge_buffer + part_buffer

parts_per_sheet = var('Parts Per Sheet', 0, '', number, frozen=False, quantity_specific=True)
if is_using_manual_nest.value == 'Yes' and first_sheet:
    parts_per_sheet.update(first_sheet.parts_per_sheet)
elif part_length > usable_sheet_length or part_width > usable_sheet_width:
    parts_per_sheet.update(0)
else:
    length_fit_count = floor(usable_sheet_length / buffered_part_length)
    width_fit_count = floor(usable_sheet_width / buffered_part_width)
    parts_per_sheet.update(min(width_fit_count * length_fit_count, part.qty))
parts_per_sheet.freeze()

number_of_sheets = var('# of Sheets', 1, '', number, frozen=False, quantity_specific=True)
if is_using_manual_nest.value == 'Yes' and nest:
    temp_number_of_sheets = 0
    for sheet in iterate(nest.sheets):
        temp_number_of_sheets += sheet.count
    number_of_sheets.update(temp_number_of_sheets)
elif parts_per_sheet > 0:
    number_of_sheets.update(ceil(part.qty / parts_per_sheet))
number_of_sheets.freeze()

# now refetch from table to get sheet cost
rows = table_lookup(
    'sheet_lookup',
    create_filter(
        filter('material', '=', part.global_material),
        filter(
            'thickness',
            'range',
            create_range(
                sheet_thickness - 0.01, sheet_thickness + 0.01
            ),
        ),
        filter('length', 'range', create_range(sheet_length - 0.1, sheet_length + 0.01)),
        filter('width', 'range', create_range(sheet_width - 0.1, sheet_width + 0.1)),
    ),
    create_order_by('sheet_cost'),
    quantity_specific=True,
)

sheet_cost = var('Sheet Cost', 0, '', currency, frozen=False, quantity_specific=True)
if rows:
    sheet_cost.update(rows[0].sheet_cost)
sheet_cost.freeze()

material_cost = 0
sheet_toggle = drop_down_var(
    'Price Calculation', 'Net Sheet Used', create_list('Total Sheets Required'), '', string
)
if sheet_toggle.value == 'Total Sheets Required':
    material_cost = sheet_cost * number_of_sheets
elif sheet_toggle.value == 'Net Sheet Used':
    if is_using_manual_nest.value == 'Yes':
        for sheet in iterate(nest.sheets):
            used_pct = sheet.yield_pct + sheet.scrap_pct
            material_cost += sheet_cost * sheet.count * used_pct
    elif parts_per_sheet > 0:
        material_cost = (1 / parts_per_sheet) * sheet_cost * part.qty

PRICE = material_cost
DAYS = 0

sheet_ref = variable_group('Sheet Reference')
sheet_ref.add_by_name(
    'Part Thickness, in',
    'Part Length, in',
    'Part Width, in',
    'Sheet Search',
    'Search Thickness, in',
    'Recommended Length, in',
    'Recommended Width, in',
    'Recommended Thickness, in',
)

sheet_vars = variable_group('Sheet Variables')
sheet_vars.add_by_name(
    'Sheet Thickness, in',
    'Sheet Length, in',
    'Sheet Width, in',
    'Is Using Manual Nest?',
)

cost_vars = variable_group('Cost Variables')
cost_vars.add_by_name(
    'Price Calculation',
    'Sheet Cost',
    'Parts Per Sheet',
    '# of Sheets',
)

param_vars = variable_group('Parts-Per-Sheet Params', default_collapsed=True)
param_vars.add_by_name(
    'Edge Buffer, in',
    'Part Buffer, in',
    'Thickness Tol, in',
)

```
