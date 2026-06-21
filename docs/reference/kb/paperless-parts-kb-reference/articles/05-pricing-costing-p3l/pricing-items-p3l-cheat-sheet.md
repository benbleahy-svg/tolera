---
title: "Pricing items P3L cheat sheet"
slug: pricing-items-p3l-cheat-sheet
source: https://help.paperlessparts.com/s/article/pricing-items-p3l-cheat-sheet
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Pricing items P3L cheat sheet

> Source: https://help.paperlessparts.com/s/article/pricing-items-p3l-cheat-sheet  
> Topic: Pricing, Costing & P3L

# Overview

Unlike costing, pricing is *subjective*. Determining the “right” price that works for your business and your customer(s) might take into account many factors, including:

- Your bottom line
- Your relationship with the customer
- The characteristics of the opportunity
- What the customer is willing to pay

**Pricing items**allow you to capture this complex decision-making by using part or opportunity information with custom formulas to calculate markup or margin % to applied to discrete categories of cost.

Pricing item formulas should end with a `PERCENTAGE =` line, specifying the percentage markup or margin to be applied to the cost category.

# Pricing item variations

Pricing items come in two variations (standard, and custom) and apply one of two formulas to arrive at price (markup or margin).

### Standard vs Custom pricing items

**Standard** pricing items are available to all customers and apply markup or margin to one of 5 discrete categories of cost--total, material, inside processing, outside processing, and purchased components-- selected when creating or editing the pricing item definition.

**Custom**pricing items are available toselect customers* and can apply markup/margin to any custom aggregation of cost by using additional P3L to analyze the part (including all assembly components) and its router (including all assembly components' routers).

In addition to `PERCENTAGE`, custom pricing items must also output a cost total with set_custom_cost(); and they typically use the the get_components() function to identify the total cost.

Note that when two instances of the same custom pricing item are applied, only the first instance's output cost will be set as the cost category ammount.

**Consult with a Paperless Parts team member to determine if your shop is eligible to use custom pricing items.*

### Markup vs Margin

**Markup** is the percentage added to cost to determine selling price.

`Markup % = (Selling Price - Cost) / Cost × 100`

**Margin** (or Gross Profit Margin) is the percentage of revenue that remains after covering costs.
`Margin % = (Selling Price - Cost) / Selling Price × 100`

``

# Available objects, variables and functions

## Common functionality

Pricing item formulas have access to the full suite of variable functionality, including `var`, `drop_down_var`, `table_var`, `variable_group`, and `table_lookup`. It also has access to all globally available math functions, such as `mean` and `median`, list functionality, workpiece and price dict (limited to pricing item communication only), access to quantity information with `get_quantities()` and `get_make_quantities()`, and the ability to rename pricing items with `set_profit_item_name(string)`.

## Pricing-item specific global objects

- `PURCHASED_COMPONENT_COST` - sum of all costs associated with purchased components in the entire assembly
- `MATERIAL_COST `- sum of all material operation costs (excluding any found within components of type purchased) in the entire assembly
- `OUTSIDE_COST` - sum of all operations with is_outside_service set to True in the entire assembly
- `INSIDE_COST `- sum of all operations that do not fit into the other three categories in the entire assembly
- `TOTAL_COST` - sum of all costs in the entire assembly
- `CALCULATION_TYPE `- determines how the output percentage value calculates its price contribution, can either be "markup" or "margin". Use globals `MARKUP` and `MARGIN` respectively to represent these strings.
- COST_CATEGORY - determines what "color of money" the output percentage references to calculate price contribution. Either "general", "purchased_component", "material", "inside", or "outside". Use globals `TOTAL_COST`, `PURCHASED_COMPONENT_COST`, `MATERIAL_COST`, `INSIDE_COST`, `OUTSIDE_COST` respectively to represent these strings.
- `CATEGORY_COST` - the dollar amount of the cost category that the pricing item is tied to. For example, if a pricing item has a `COST_CATEGORY` == "material", `COST` == `MATERIAL_COST`
- contact - global object containing attributes about the contact & account associated on the quote. Same attributes as with operation P3L.
- `REQUESTED_QUANTITY` - customer requested quantity

## Pricing-item specific global functions

NOTE: the following only includes functions that are *not* included in operation P3L.

`set_profit_item_name(name: str)`

Dynamically renames the pricing item based on the string name argument. If this function is not called, the name will default to the name of the operation definition in your processes page.

`get_components(order: 'leaf_to_root' | 'root_to_leaf')`

Retrieves a flat list of components in the assembly, ordered based on the specified order. Can be combined with a for…each statement (for component in get_components()) to iterate through each entry.

See the below “kitchen sink” example for the complex syntax of all sub-objects.

`set_custom_cost(cost: number`) (quantity-break-specific) **[custom pricing items only]**

For custom pricing items only - set the cost amount that the PERCENTAGE will be applied to, specific to each quantity break.

## Not available in pricing items

Pricing item P3L does NOT have access to a lot of operation P3L functionality. This includes: - The part object - Custom attributes with `set_custom_attribute` and `get_custom_attribute` - Requesting interrogations e.g. `analyze_mill3()` - Accessing child info with `get_child_info()`

# Examples

``

## Standard pricing item example

The following example demonstrates how to implement a very basic customer specific markup. An extension of this implementation would be to use a custom table lookup to dynamically fetch markup percentages based on account name. The settings for this pricing item are calculation type of markup and cost category of general.

```
markup_factor = var('Markup Factor', 1.0, '', number, frozen=False)
if contact:
	if contact.account.name == 'Pint Drinker Machine':
		markup_factor.update(1.5)
markup_factor.freeze()
base_percentage = var('Base Percentage', 10, '', number)

PERCENTAGE = markup_factor * base_percentage
```

## Custom pricing item “kitchen sink”

```
# can iterate through a flat list of components, either leaf_to_root or root_to_leaf (default is root_to_leaf)
for component in get_components(order='leaf_to_root'):
    # the new component object gives access to several new things
    component.uuid
    component.part_uuid
    # total cost of all materials, operations, and any unit cost overrides
    component.self_cost
    # summed lead time of process lead time + materials and operations lead time contributions
    component.lead_time

    # optional process object
    process = component.process
    if process:
        process.name
        # lead time in business days of the default lead time specified on the process
        process.lead_time

    # access to the entire existing part object through component.part
    part = component.part
    part.innate_quantity
    part.is_root_component
    part.part_number
    part.revision
    part.obtain_method
    part.is_assembly
    part.purchased_component
    part.material
    part.global_material
    part.material_family
    part.material_class
    part.density
    part.weight
    part.mat_cost_per_volume
    part.mat_added_lead_time
    part.size_x
    part.size_y
    part.size_z
    part.max_dim
    part.med_dim
    part.min_dim
    part.area
    part.volume
    part.quantities
    part.make_quantities
    part.bom_quantities
    part.qty
    part.bom_qty
    part.count_purchased_children
    part.count_manufactured_children

    # access to the standard purchased_component object
    purchased_component = part.purchased_component
    if purchased_component:
        purchased_component.oem_part_number
        purchased_component.piece_price
        purchased_component.internal_part_number
        purchased_component.description
        # and you can access the rest of the custom fields i.e. purchased_component.bag_price

    # can access a list of direct children beneath the component (child BOM)
    for child_entry in get_children(component):
        # component object of the child
        child_entry.component
        # count of child beneath the parent (not necessarily the entire innate quantity since the child could be in multiple locations in the BOM)
        child_entry.count

    # can access any custom attribute on the component, specifying a default value if not found
    component.get_custom_attribute('attribute_name', 'other_value')

    # can iterate through operations, can pass a component object or a component.uuid to access this list
    # for op in get_operations(component.uuid):  # also valid access pattern
    for op in get_operations(component):
        op.cost
        op.lead_time
        op.runtime
        op.setup_time
        op.name
        op.category
        op.is_outside_service
        op.is_finish
        # can grab both numeric and string based variables, providing a default value for if that variable is not found
        op.get_variable('variable_name', 'a')
        # can grab drop down variable value, but not options, also providing default value in case not found
        op.get_variable('ddv1', 10)

        # can access op_def object (could be None for manual operations)
        op_def = op.op_def
        if op_def:
            op_def.name
            op_def.erp_code

    # can iterate through material operations as well, getting access to everything we see above with operations
    # for material in get_material_operations(component.uuid):  # also valid access pattern
    for material in get_material_operations(component):
        material.lead_time
        material.cost

# required to call the set_custom_cost(number) function
set_custom_cost(0)
PERCENTAGE = 100
```
