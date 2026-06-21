---
title: "Operation P3L cheat sheet"
slug: operation-p3l-cheat-sheet
source: https://help.paperlessparts.com/s/article/operation-p3l-cheat-sheet
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Operation P3L cheat sheet

> Source: https://help.paperlessparts.com/s/article/operation-p3l-cheat-sheet  
> Topic: Pricing, Costing & P3L

The purpose of operation P3L is to generate a cost and lead time for each quantity break on a part for the operation. Operation P3L provides some special objects, variable names, and functions to make costing easy. You also have the full mathematical capability of Python.

## Special Objects and Variables

- part – global object containing attributes that describe the geometry and manufacturing specification for a part
- quote – global object containing attributes about the quote, including contact, account, estimator salesperson, and facility
- COST – special variable name for the calculated cost; every P3L program should declare a variable with this name to set an extended cost for the specified part and quantity
- DAYS – special variable name for calculated lead time, in business days; every P3L program should declare a variable with this name to specify a number of business days lead time to be added for this operation; use DAYS = 0 if this operation does not add a day to lead time

## The Part Object

The costing program gets information about the part and manufacturing specification via the `part` object. This object has a number of attributes accessible with the “dot” operator, such as `part.volume`. By default, all attributes are in metric units. You can convert all values to US units by beginning your costing program with `units_in()`.

| Attribute | Description | Metric units | Imperial units |
| --- | --- | --- | --- |
| `part.size_x` | **3D files:** The first non-null property of: Overwritten X dimensionMaximum dimension of optimal bounding boxX dimension of axis aligned bounding box **2D files:** X dimension of file or overwritten X dimension   **Non-geometric files:** Manually inputted X dimension | mm | in |
| `part.size_y` | **3D files:** The first non-null property of: Overwritten Y dimensionMedian dimension of optimal bounding boxY dimension of axis aligned bounding box **2D files:** Y dimension of file or overwritten Y dimension   **Non-geometric files:** Manually inputted Y dimension | mm | in |
| `part.size_z` | **3D files:** The first non-null property of: Overwritten Z dimensionMinimum dimension of optimal bounding boxZ dimension of axis aligned bounding box **2D files:** Inputted thickness or overwritten Z dimension   **Non-geometric files:** Manually inputted Z dimension | mm | in |
| `part.max_dim` | Maximum dimension of optimal bounding box | mm | in |
| `part.med_dim` | Median dimension of optimal bounding box | mm | in |
| `part.min_dim` | Minimum dimension of optimal bounding box | mm | in |
| `part.area` | Surface area | mm^2 | in^2 |
| `part.volume` | Volume | mm^3 | in^3 |
| `part.qty` | Make quantity | n/a | n/a |
| `part.bom_qty` | Quantity to deliver to customer for the calculation's quantity break | n/a | n/a |
| `part.innate_quantity` | Quantity to deliver to the customer for a single top-level part; aka assuming a quantity break of 1 | n/a | n/a |
| `part.material` | Name of material (e.g. Aluminum 6061-T6, Tool Steel A2) (defers to custom naming if present) | n/a | n/a |
| `part.global_material` | Name of material as it exists in the Paperless Parts global materials database (e.g. Aluminum 6061-T6, Tool Steel A2) | n/a | n/a |
| `part.material_family` | Name of material family (e.g. Aluminum, Stainless Steel) | n/a | n/a |
| `part.material_class` | Name of material class (e.g. Metal, Polymer) | n/a | n/a |
| `part.weight` | Weight of part | g | lb |
| `part.density` | Density of part | g/cm^3 | lb/in^3 |
| `part.mat_cost_per_volume` | Material cost per unit volume | $/mm^3 | $/in^3 |
| `part.mat_added_lead_time` | Added lead time for material selection (configured in process) | days | days |
| `part.is_root_component` | True/False indicating if the part is the root of the assembly tree | n/a | n/a |
| `part.obtain_method` | Component obtain method, ( `PURCHASED`or `MANUFACTURED`). All manufactured components and subassemblies have an obtain_method = `MANUFACTURED` | n/a | n/a |
| `part.is_assembly` | True/False. Will be true if the component is a subassembly | n/a | n/a |
| `part.part_number` | Part number | n/a | n/a |
| `part.revision` | Part revision | n/a | n/a |
| `part.count_manufactured_children` | Total count of components with obtain method manufactured in the child BOM (includes subassemblies) | n/a | n/a |
| `part.count_purchased_children` | Total count of components with obtain method purchased in the child BOM | n/a | n/a |
| `part.quantities` | List of quantities on the part | n/a | n/a |
| `part.bom_quantities` | List of BOM quantities for part, matching quantities indicies | n/a | n/a |
| `part.make_quantities` | List of make quantities on the part, matching quantities indices | n/a | n/a |
| `part.purchased_component` | Reference to purchased component tied to part, could be `None` or a "dot" operator object (see below) | n/a | n/a |

| **Attribute** | **Description** | **Units** |
| --- | --- | --- |
| `part.purchased_component.oem_part_number` | Name of purchased component, usually the OEM part number | n/a |
| `part.purchased_component.internal_part_number` | The internal part number of the purchased component (optional) | n/a |
| `part.purchased_component.piece_price` | Piece price to 4 decimal places | $ |

**NOTE**: The `part.purchased_component` object can also "dot" into more properties. These additional properties are dictated by the custom columns you configure in the purchased components tab in the processes page. Refer to [our purchased components documentation](https://help.paperlessparts.com/s/article/purchased-components) for more information on how to set up these columns.

## The Operation Definition Object

The costing program provides information about its definition.

| **Attribute** | **Description** |
| --- | --- |
| `op_def.name` | The operation definition's name. |

## The Line Item Object

The costing program gives information about the line item, currently including export-controlled status.

``

| **Attribute** | **Description** |
| --- | --- |
| `line_item.is_export_controlled` | Whether the line item being quoted has been marked export-controlled. |

## The Quote Object

The costing program gives information about the quote, including, account, contact, estimator, salesperson, and facility. All attributes are accessible via the "dot" operator, just as with the part object, such as `quote.contact.first_name`

When using these attributes, **note the following:**

- P3L based on these attributes will *not*automatically refresh when fields change—users will need to refresh pricing after setting the value.
- Because these fields may be empty, P3L authors must check for the values before use.. i.e. if quote.contact ... <logic_with_quote_contact>

| **Attribute** | **Description** |
| --- | --- |
| `quote.account.name` | Account name |
| `quote.account.erp_code` | Code that relates the account to an integrated ERP system. Contact support for more information on setting this up. |
| `quote.account.UUID` | Account's UUID |

| **Attribute** | **Description** |
| --- | --- |
| `quote.contact.email` | Contact's email address |
| `quote.contact.first_name` | Contact's first name |
| `quote.contact.last_name` | Contact's last name |
| `quote.contact.full_name` | Contact's full name |
| `quote.contact.uuid` | Contact's UUID |

| **Attribute** | **Description** |
| --- | --- |
| `quote.estimator.email` | **Quote's**assigned estimator's email address |
| `quote.estimator.first_name` | **Quote's**assigned estimator's first name |
| `quote.estimator.last_name` | **Quote's**assigned estimator's last name |
| `quote.estimator.full_name` | **Quote's**assigned estimator's full name |
| `quote.estimator.erp_code` | Code that relates the **quote's**estimator to an integrated ERP system. Contact support for more information on setting this up |
| `quote.estimator.uuid` | **Quote's**assigned estimator's UUID |

| **Attribute** | **Description** |
| --- | --- |
| `quote.salesperson.email` | Assigned salesperson's email address |
| `quote.salesperson.first_name` | Assigned salesperson's first name |
| `quote.salesperson.last_name` | Assigned salesperson's last name |
| `quote.salesperson.full_name` | Assigned salesperson's full name |
| `quote.salesperson.erp_code` | Code that relates the salesperson to an integrated ERP system. Contact support for more information on setting this up. |
| `quote.salesperson.uuid` | Assigned salesperson's UUID |

| **Attribute** | **Description** |
| --- | --- |
| `quote.facility.name` | Assigned facility's name |
| `quote.facility.uuid` | Assigned facility's UUID |

## Available Python Functions and Operators

The built-in Python functions listed below are available for your use. For more information, see [Python 3.6 documentation](https://docs.python.org/3.6/library/functions.html).

`min()`

Can be called on an iterable object (e.g., a list) or by passing multiple numerical arguments. Returns the minimum value passed in.

`max()`

Can be called on an iterable object (e.g., a list) or by passing multiple numerical arguments. Returns the maximum value passed in.

`mean()`

Can be called on an iterable object (e.g., a list) or by passing multiple numerical arguments. Returns the mean of the arguments.

`median()`

Can be called on an iterable object (e.g., a list) or by passing multiple numerical arguments. Returns the median of the arguments.

`round(number[, ndigits])`(

Round **number** to nearest integer. If **ndigits** is provided, then the number will be rounded to the specified number of decimal places.

`abs(number)`

Return the absolute value of **number**.

`sum(iterable[, start])`

Return the sum of all values in **iterable** (e.g., a list). Optionally, a **start** value can be passed to start the sum at a number other than 0.

`floor(x)`

Return the floor of **x** as an integer. This is the largest integer <= x.

`ceil(x)`

Return the ceiling of **x** as an integer. This is the smallest integer >= x.

`str(x)`

Return the value of **x** as a string.

`format(args)`

You can construct dynamic strings using `''.format()`. This is useful for operation naming and table lookups. Look to the general python docs for more info on this function.

`split(x)`

Split the any string by the character specified by **x**. You would use this function on strings you want specific pieces of, for example splitting the part material name by spaces `part.material.split(' ')`. You can then index into the output of split to grab the piece you need. Look to the general python docs for more info on this function.

The following Python operators are available for performing mathematical operations:

- Basic mathematical operators, *, /, +, and -.
- Augmentation assignments like +=, -=, *=, and /=
- Exponentiation, **, for example 10**2 represents “ten squared” and equals 100.
- Comparison operators <, <=, >, and >= for use in if statements
- Use and and or to create complex if conditions

## P3L Functions

`no_quote()`

Call this function at any point to “no quote” this part and quantity. If this function is executed at any point in the program, the value of `COST` is ignored and that operation and quantity will show a blank cost. The call to this function cannot be “undone” within the same run of a program.

`units_mm()`

Call this function as your first statement to explicitly keep the part object in metric units. Measurements will be in millimeters, square millimeters, or cubic millimeters, depending on the value. Calls to this function after the first statement will result in an error. Note that calling this function is optional because part data is in metric by default.

`units_in()`

Call this function as your first statement to convert the part object into US units. Measurements will be inches, square inches, or cubic inches, depending on the value. Calls to this function after the first statement will result in an error.

`analyze_mill3()`

Analyze this part for three-axis milling and return an object containing the calculated attributes. See [Three-Axis Milling](https://help.paperlessparts.com/s/article/milling-process).

`analyze_lathe()`

Analyze this part for lathe/turning and return an object containing the calculated attributes. See [Lathe](https://help.paperlessparts.com/s/article/lathe-process).

`analyze_sheet_metal()`

Analyze this part for a sheet metal process and return an object containing the calculated attributes. See [Sheet Metal](https://help.paperlessparts.com/s/article/sheet-metal-process).

`analyze_tube_laser()`

Analyze this part for a tube laser process and return an object containing the calculated attributes. See [Tube Laser](https://help.paperlessparts.com/s/article/tube-laser-process).

`analyze_wire_edm()`

Analyze this part for a wire EDM process and return an object containing the calculated attributes. See [Wire EDM](https://help.paperlessparts.com/s/article/wire-edm-process).

`analyze_casting()`

Analyze this part for a casting process, like cast urethane, and return an object containing the calculated attributes. See [Cast Urethane](https://help.paperlessparts.com/s/article/cast-urethane-process).

`analyze_additive()`

Analyze this part for an additive process, and return an object containing the calculated attributes. See [Additive](https://help.paperlessparts.com/s/article/additive-process)for more information, including how to get printer-specific values.

`manual_nest()`

Gather results created by the nesting module and return an object containing the nesting results. See [Manual Component Nesting](https://help.paperlessparts.com/s/article/manual-component-nesting) for more information.

```
var(
    name,
    default,
    description,
    value_type,
    default_visible=True,
    frozen=True,
    quantity_specific=False
)
```

Declare an operation variable whose value can be managed on the processes page. Variables make it easy to modify numbers that change occasionally, such as labor and shop rates, without modifying program code. Operation variables can also be overridden on the quote page for a particular quote item. We recommend creating variables for any value you may want to check or override while quoting an operation. Think of this function as a way to create custom interfaces for each operation you create. Every time you use this function, a variable entity will be available to override in the operation UI at quote time.

**NOTE: This cannot be called from within an if/elif/else statement or from within a loop.**

**name** is the unique name of the variable. **name** can be any string, but there are two special names, `setup_time` and `runtime`, that will make these variables appear in the operations list for a quote item. See the “Runtime and Setup Time Variables” section below for more information on this naming convention and how these special variables work. **default** is the default value, which can be changed from the processes page or overridden for a particular quote item. The default value is computed once only when the program is saved and cannot depend on the part or other variables. **description** is optional and is displayed when editing the value from the processes page. **value_type** can be either `number` , `currency`or `string`. If the **value_type** is `number` or `currency`, the value will be casted to a floating point number, and the compiler will enforce numeric typing on any values the variable is updated with. If the **value_type** is `string`, the value will be casted to a string and string typing will be enforced on any values the variable is updated with. `default_visible` is optional and can be set to `False` to not show by default on the processes page; this is useful for operations with a large numbers of variables. **frozen** specifies whether the variable’s value can dynamically depend on the part or other values in the program; use `frozen=False` to create a “dynamic variable”. See the section below for more information on how to use dynamic variables. **quantity_specific** specifies whether the variable's value will be displayed and overriden along individual quantity breaks. Check out the article on [quantity-specific variables](https://help.paperlessparts.com/s/article/quantity-specific-variables) for more information.

Returns the value of the variable after applying overrides.

```
table_var(
    name: str,
    description: str,
    table_name: str,
    filters: List[filter | exclude],
    order_by: List[str],
    display_column_name: str,
    frozen: bool = True,
    quantity_specific: bool = False
) -> TableRow
```

Declare a table variable that allows you to perform look ups to any [custom tables](https://help.paperlessparts.com/s/article/custom-tables) you have set up. Will return the first row that satisfies the **filters** sorted by the **order_by** conditions. If no rows satisfy the **filters**, will return `None`. You can perform filtering operations against rows on any sort of table. The filter conditions can be informed by attributes of the part or surrounding operation variables. The value for this variable can be overridden through the live costing interface at quote time. This is an incredibly powerful feature that can solve nearly any costing situation. Check out our in depth article on table variables [here](https://help.paperlessparts.com/s/article/custom-table-p3l) .

**NOTE: This cannot be called from within an if/elif/else statement or from within a loop.**

```
table_lookup(
    table_name: str,
    filters: List[filter | exclude],
    order_by: List[str],
    quantity_specific: bool = False
) -> P3LList[TableRow]
```

Similar to the `table_var` function above, except it returns a P3LList of row objects that satisfy the **filters** instead of just the first row. This DOES NOT create a new variable entity that can be overridden in the live costing interface. This is used as a utility to perform more flexible table lookups and to collect larger chunks of data to work with in your costing formulas. Check out our in depth article on table variables [here](https://help.paperlessparts.com/s/article/custom-table-p3l).

**NOTE: This cannot be called from within an if/elif/else statement or from within a loop.**

```
variable_group(
    name: str,
    default_collapsed: bool = False
)
```

Declare a group of variables that will collect `var` and `table_var` objects into ordered groups on the quoting interface. To add a variable or table variable to a variable group, use the `add_by_name(variable_name)` method. The ordering of the variable groups on the quoting interface will match the order that these groups are declared in the costing formula. Additionally, the order in which you add variables via the `add_by_name(variable_name)` method will determine the ordering of the variables within the variable group in the quoting interface. The `default_collapsed` input will determine whether the variable group is by default NOT expanded on the quoting interface. This value is default `False`. Specifying `default_collapsed=True` is useful for costing variables that do not change often and do not need to clutter the interface in most occasions, such as machine and labor rates. See the section below for more information on usage.

**NOTE: This cannot be called from within an if/elif/else statement or from within a loop.**

```
drop_down_var(name: str,
    default_value: str,
    default_options: P3LList,
    description: str,
    value_type: str,
    frozen: bool = True,
    quantity_specific: bool = False
) -> DropDownVariable<br>
```

Declare a drop down variable with a discreet number of options that can be selected as the value. This is a very useful variable type especially for implementing "logic switches" in an operation program. In more advanced applications, you can even use drop down variables to create dynamic forms where available options can change as variables and geometric properties of the part change. Check out out in depth article on [drop down variables](https://help.paperlessparts.com/s/article/drop-down-variables) for more info.

**NOTE: This cannot be called from within an if/elif/else statement or from within a loop.**

`set_operation_name(name)`

Set the name of the operation as it would appear in the user interface. If this function is not called, the name will default to the name of the operation definition in your processes page. This function is particularly useful if your operation naming convention depends on part attributes (such as a thickness of a sheet metal part or material) or on operation ordering (such as CNC Op-1).

**name** is the string you would wish to rename the operation.

HINT: Combine this function with string variables and string drop down variables to be able to rename your operation dynamically at quote time.

`set_notes(notes: string)```

Set the notes for the operation, add-on, pricing item, or discount. Notes are displayed in the quoting interface.

**notes** is the string you would wish to set the notes to.

HINT: Use with `list.join()` to convert a list of strings to a multi-line note or use the `set_notes_from_list()` helper function.

`set_workpiece_value(key, value)`

Set the **value** indicated by the **key** in **workpiece** dictionary object.

**key** is a string, **value** is any type.

`get_workpiece_value(key, default_value)`

Access the variable stored in the **workpiece** indicated by the **key**. The **default_value** is what this function will return if the **key** provided is not found within the workpiece.

**key** is a string, **default_value** is any type.

`is_close(n1, n2, tol=0.001)`

Compare two numbers **n1** and **n2** with the specified tolerance **tol**. The tolerance defaults to 0.001. Use this for numerical comparisons to prevent issues with floating point numbers.

**n1** is a number, **n2** is a number, and **tol** is a number.

`is_a_in_b(a, b)`

Check if **a** is in **b** based on the built-in `in` Python operator. This is a useful catch all function that can help when mixing different types of dynamic variables, built-in strings, floats, and P3L List entities. Because of Python's type enforcement for the `in` operator, this function is necessary when checking to see if a dynamic string variable is inside a built a Python string. But it can be used with a mix of several different object types. Use it with if conditional statements e.g. `if is_a_in_b('hello', 'hello world')`.

**a** is any, **b** is a string, dynamic string variable, or P3LList instance.

`get_cost_value(key)`

Get the cost value of a cell(s) with an operation name or operation definition name that matches the **key** value for the quantity currently being calculated. Additionally, you can use special key values to get accumulated values. Using `--material--` as the key will return the total cost of all material cells. Using `--outside--` as the key will return the total cost of all cells belonging to an operation tagged as an outside operation. Using `--inside--` as the key will return the total cost of all cells belonging to operations not marked as outside or material. Using `--total--` as the key will return the total cost of all cells.

**key** is a string, including usage of the special keys e.g. `get_cost_value('--material--')`

`set_custom_attribute(key, value)`

Set the **value** indicated by the **key** to the custom attributes of the part. See the "Custom Part Attributes" section below for more information.

**key** is a string, **value** must be a number, Boolean, or string value. When setting a pre-existing custom part attribute with a value that does not match the type of the existing value, the program will fail to execute.

`get_custom_attribute(key, default_value)`

Access the value stored in the custom attributes of the part indicated by the **key**. The **default_value** is what this function will return if the **key** provided is not found within the custom part attributes.

**key** is a string, **default_value** is any type.

`get_quantities() -> P3LList`

An iterator function that allows you to loop through all root bom quantities on the part. You would use this with a for loop, e.g. `for quantity in get_quantities()`.

`get_bom_quantities() -> P3LList`

An iterator function that allows you to loop through all the bom quantities on the part. You would use this with a for loop, e.g. `for quantity in get_bom_quantities()`. The make quantities are lined up by index to their respective quantities from `get_quantities()`.

`get_make_quantities() -> P3LList`

An iterator function that allows you to loop through all make quantities on the part. You would use this with a for loop, e.g. `for make_qty in get_make_quantities()`. The make quantities are lined up by index to their respective quantities from `get_quantities()`.

```
get_children(
    obtain_method=None,
    is_assembly=None,
    recursive=False
) -> P3LList
```

An iterator function that allows you to loop through the information about the children to the active component. This is useful when creating assembly and hardware insertion operations. This function returns an array of data objects that describe the information of descendants of the active component. The obtain_method argument is optional, but can be a value of PURCHASED or MANUFACTURED. If you do not specify an obtain_method, it will return descendants of all obtain_methods. If you do specify an obtain_method, it will only return information on descendants of that inputted obtain_method. The is_assembly argument is optional, but can be a value of True or False. If you do not specify an is_assembly, it will return descendants marked either as True or False for is_assembly. If you do specify an is_assembly, it will only return information on descendants where is_assembly matches the input value. The recursive input dictates whether you want to collect information for children with respect to the flat BOM (all components and their counts with respect to the whole assembly tree) or only return information for children with respect to the direct child BOM (only components that related directly to the active component). What this means is that based on the components location in the assembly tree, collecting information with respect to the flat BOM would recursively collect all the information about its descendants until the bottom of the tree. Collecting information with respect to the child BOM would only give information on components in the assembly tree that are direct children of the active component.

The data object this function returns can access its attributes via "dot" operator. The attributes of the `child` objects in the returned array are:

| **Attribute** | **Description** |
| --- | --- |
| `child.obtain_method` | Obtain method of the component ( `PURCHASED`or `MANUFACTURED`). All manufactured components and subassemblies have an obtain_method of MANUFACTURED |
| child.is_assembly | True/False |
| `child.part_number` | Part number of the component |
| `child.revision` | Revision of component |
| `child.count` | Total count of this descendant in relation to the component. If `recursive=True` this will be the count of the child component to the base of the tree. If `recursive=False` this will be the count of the child component as it related only to the active component |
| `child.purchased_component` | The purchased component tied to the child. Can be `None`, otherwise has same properties of purchased component table above |

Check out the assembly style operations section below for more details on how to use this function.

## Dynamic Variables

By default, variables are “frozen”, which means their default values are computed only when the program is saved, without access to the global `part` object. Sometimes, you will want to compute the variable’s value dynamically, have that value appear in the operations user interface, and optionally be overridden on a particular quote.

To use a dynamic variable, first declare a variable and set `frozen` to `False`:

```
my_var = var('My Variable', 0, '', number, frozen=False)
```

In this example, the value of `my_var` will initially be the specified default value of `0`. Suppose you want this variable to represent the largest dimension of the part. You can change the value of this variable like this:

```
my_var.update(max(part.size_x, part.size_y, part.size_z))
```

This new value will be shown in the user interface when you view this operation on a quote. If the largest dimension is 10, then the value of `my_var` will be `10` at this point in your program. You can update the value multiple times while the variable is un-frozen. Note that the quote page allows this value to be overridden. In order to use this overridden value, you must “freeze” this variable. A dynamic variable should be frozen after you are finished updating it and before you use its value to calculate cost, like in this example:

```
my_var.freeze()

if my_var > 15: COST = 50

else: COST = 25
```

Continuing with our example where the largest dimension is `10`, `my_var` will be `10` if no override value was specified by the user at quote time. Therefore the cost will be 25. However, if the user instead enters `20` as the override on the quotes page, then `my_var` will be `20` and the cost *will be* doubled. Note that the override is applied to the variable at the location you call freeze.

**Note: Variables are designed to be use for the operation across all quantities. If you need a variable to be quantity specific, you need to set**quantity_specific=True **when defining the variable. If you do not do this, updating the variable with values that are quantity specific will not give correct calculations.**

## Runtime and Setup Time Variables

The quoting user interface handles variables with the **name** of `runtime` and `setup_time` in a special way. These variables are shown directly on the operations list, without having to open the operations modal. Using dynamic variables, you can have full control over what values are shown here. As the simplest example, you could have setup time always default to 0 unless overridden by adding this line to your program:

```
setup_time = var('setup_time', 0, '', number)
```

NOTE: Within the P3L program, the `runtime` and `setup_time` variables are in units of hours. However, the units these values are displayed in the quoting interface can be customized to *minutes*, *hours*, or *seconds*. When overriding variables at quote time, your overrides will be applied in the display units you have specified. For example, if you override **runtime** in the user interface to 30 minutes, the **runtime** variable will have a value of 0.5 . We suggest keeping your time variables in units of hours so they can be multiplied by an hourly rate to calculate cost.

## Variable Groups

The quoting interface lines out variables by default into two collapsible groups: **primary** and **declared**. The variables in the **primary** group are the special `runtime` and `setup_time` variables discussed above. The variables in the **declared** group are any other variables or table variables declared in the costing program. While this default interface is effective for straightforward operations with a limited number of costing variables, when the operation gets more complicated and the number of variables increases, it can be useful to group variables into explicit sections to make it easier to work through the operation at quote time. To establish additional variable groups, you can use the `variable_group(name, default_collapsed)` function. This will return a group that you can add declared variables and table variables to in an any order you specify. This will then separate these variables into its own collapsible group on the quoting interface. Here is an example of how to use variable groups:

```
labor_rate = var('Labor Rate', 50, '$/hr', currency)
machine_rate = var('Machine Rate', 40, '$/hr', currency)

rates = variable_group('Rates', default_collapsed=True)
rates.add_by_name('Labor Rate', 'Machine Rate')

tapped_hole_count = var('Tapped Hole Count', 0, 'Number of tapped holes', number)

inputs = variable_group('Manual Inputs') # not specifying default_collapsed will default it to False
inputs.add_by_name('Tapped Hole Count')

runtime_per_hole = var('Runtime Per Hole', 2, 'Time per tapped hole in minutes', number)
setup_time_per_hole = var('Setup Time Per Hole', 5, 'Time per tapped hole in minutes', number)

time_vars = var('Time Contributions', default_collapsed=True)
time_vars.add_by_name('Runtime Per Hole', 'Setup Time Per Hole')

# NOTE: you cannot add special variables runtime and setup_time to groups

runtime = var('runtime', 0, 'Total runtime in hours', number, frozen=False)
runtime.update(tapped_hole_count * runtime_per_hole / 60)
runtime.freeze()

setup_time = var('setup_time', 0, 'Total setup time in hours', number, frozen=False)
setup_time.update(setup_time_per_hole * tapped_hole_count / 60)
setup_time.freeze()

COST = runtime * part.qty * machine_rate + setup_time * labor_rate
```

## Workpiece

The **workpiece** is a dictionary that can be used to store and access variables within an operation and even across operations. To interface with the **workpiece**, you must store any defined or calculated variables with a `key-value`pair inside of an operation formula. You do this using the `set_workpiece_value` function. Any operations that follow the operation where you use `set_workpiece_value` will now have access to the value you stored via the `key-value` pair relationship. In subsequent operations, you can access information stored in the workpiece using `get_workpiece_value`. A helpful use case for the workpiece involves passing overridden operation variables to downstream operations. For example, say you have a hole tapping operation where you specify the count of tapped holes. A downstream Anodize op then requires any tapped holes to be masked. We can pass the number of tapped holes we use to cost the Tapping operation to our Anodize op. Here is our Tapping operation:

```
tapped_hole_count = var('Tapped Hole Count', 0, 'Number of tapped holes', number)
set_workpiece_value('tapped_hole_count', tapped_hole_count)
runtime_per_hole = var('Time Per Hole', 3, 'Time per tapped hole in minutes', number)
runtime = var('runtime', 0, 'Total runtime in hours', number, frozen=False)
runtime.update(tapped_hole_count * runtime_per_hole / 60)
runtime.freeze()
rate = var('Rate', 50, '$/hr', currency)

COST = rate * runtime * part.qty
DAYS = 0
```

As you can see, we set the value of `tapped_hole_count` with the number of tapped holes we specify at quote time. Now let us access this value in our Anodize operation, where we will apply a cost for each of the maskings:

```
num_tapped_holes = get_workpiece_value('tapped_hole_count', 0)
num_maskings = var('Number of Maskings', 0, 'Number of maskings required to anodize', number, frozen=False)
num_maskings.update(num_tapped_holes)
num_maskings.freeze()
cost_per_masking = var('Cost Per Masking', 1, '$ per mask', currency)
mask_cost = cost_per_masking * num_maskings * part.qty
piece_price = var('Piece Price', 1.25, 'Piece price in dollars', currency)

COST = piece_price * part.qty + mask_cost
DAYS = 0
```

By accessing the value of `tapped_hole_count` we can quickly can grab costing elements from previous operations without having to copy and past code from our Tapping operation and without having to input tapped hole count more than once.

It is important to know that the workpiece follows cost calculation along quantity lines. This means that the workpiece will flow through every operation for one quantity, and then the next, and so on.

## Accessing Surrounding Costs

Similar to the workpiece, there is a **cost****dictionary** that gets passed from operation to operation that contains cell costing. For every cell executed before the current operation, we store the cost value of the cell (either calculated or overridden), as well as the accumulated sum of different groups of cells belonging to certain operation types. The way you access these cost values is using the `get_cost_value(key)` function. The key you pass into the function to access specific operation costing can be either the operation name or operation definition name. So if an operation definition is named **Material Sheet** and you use the `set_operation_name(part.material)` function, you can access the costing of that Material Sheet operation using either `get_cost_value('Material Sheet')` or `get_cost_value(part.material)`. The value returned from that function will be the sum of all cells with either operation names or operation definition names that match the specified key. You can also access accumulated sums of costs from cells of different groups. You can access the sum of all cells marked as material operations using `--material--`. You can access the sum of all cells marked as outside operations using `--outside--`. You can access the sum of all cells not marked as material or outside using `--inside--`. You can access the total sum of all cells by using `--total--`. A simple use case for this function is to apply a markup to material. This material markup op is seen below:

```
markup = var('markup', 0.3, '', number)
set_operation_name('{} markup'.format(part.material))

COST = get_cost_value('--material--') * markup
DAYS = 0
```

Similar to the workpiece, cost calculation follows along quantity lines. This means that the cost dictionary will flow through every operation for one quantity, and then the next, and so on.

## Purchased Component Costing

Costing purchased components uses the same process/operations interface that we use to cost assembled and manufactured components. In the processes page, you can specify a process as your default purchased component process. What this means is whenever a purchased component gets assigned or added in an assembly, that process will automatically be applied to that component. By default, your account is loaded with a process that uses a single operation to cost purchased components. That operation uses the piece_price on the component to generate a cost. That operation looks something like the following:

```
piece_price = var('piece_price', 0, '', currency, frozen=False)

if part.purchased_component:
    piece_price.update(part.purchased_component.piece_price)

piece_price.freeze()
COST = piece_price * part.qty

DAYS = 0
```

This is the most simple example of how to cost purchased components. You can interact with any of the information described on this page to come up with whatever custom costing logic you want.

## Assembly Costing

Costing for assembly operations utilizes the information in the `part` object about the descendants of the active component. A simple way to cost assemble time is by having one assemble operation on the top-level root assembly that interacts with the insertion times specified on the `purchased_component` objects from `get_children()`. Here is one such example:

```
runtime = var('runtime', 0, '', number, frozen=False)
rts = 0

for child in get_children(obtain_method=PURCHASED, recursive=True):
    if child.purchased_component.insertion_time:
        rts += child.purchased_component.insertion_time * child.count

runtime.update(rts / 3600)
runtime.freeze()
rate = var('Rate', 60, '$/hr', currency)

COST = runtime * rate * part.qty
```

Alternatively, you can set up an operation that breaks down assembly costs at each individual subassembly level. This allows for a more clear organization of assembly costs as you are quoting large assemblies with potentially dozens of subassemblies beneath them. The only change we have to make to the above operation to enable this costing strategy is specifying `recursive=False` to the `get_children()` function.

```
runtime = var('runtime', 0, '', number, frozen=False)
rts = 0

for child in get_children(obtain_method=PURCHASED, recursive=False):
    if child.purchased_component.insertion_time:
        rts += child.purchased_component.insertion_time * child.count

runtime.update(rts / 3600)
runtime.freeze()
rate = var('Rate', 60, '$/hr', currency)

COST = runtime * rate * part.qty
```

When using the formula, you will need to apply this operation to every subassembly in the assembly breakout to ensure you encapsulating all assembly costs for the entire assembly tree.

NOTE: If you do not have insertion times specified on individual purchased components, you can instead use a flat rate or time per purchased component.

NOTE: If you get an attribute notRefer to our [managing purchased components](https://help.paperlessparts.com/s/article/purchased-components) resource to set up this attribute.

## Custom Part Attributes

Custom part attributes are top-level properties stored on a part that you can access in P3L. Custom part attributes can be set or created manually at quote time or can be set dynamically from within P3L. Custom part attributes can be useful when there are inputs that influence costing that cannot necessarily be automatically extracted from the files you receive from customers. A universal example is the presence of critical tolerances. When a part has critical tolerances, run times are usually drastically higher. Let's say we have a custom part attribute with the name `has_critical_tolerances`. The operation below demonstrates how to access this custom attribute and use it to affect costing.

```
units_in()
has_critical_tolerances = get_custom_attribute('has_critical_tolerances', False)
mill3 = analyze_mill3()
runtime = var('runtime', 0, '', number, frozen=False)

if has_critical_tolerances:
    runtime.update(mill3.runtime * 1.25)
else:
    runtime.update(mill3.runtime)

runtime.freeze()

COST = runtime * part.qty * 50
```

These custom part attributes can also be set dynamically from within P3L to avoid having to manually input them for every part. This is useful if your shop gets a healthy mix of geometric and non-geometric files. Let's say you have a turning process where the part diameter and length are required to cost out several of your operations. If you receive a step file, Paperless can use its interrogations to automatically extract those values for you. However, if you receive a PDF, you will have to input those values manually. By dynamically setting and getting custom attributes you can streamline your quoting efforts and consolidate your P3L code to work well for both geometric and non geometric files. Let's take a look at a sample grinding operation for that turning process. Let's say there are two custom attributes, `outer_diameter` and `part_length` that influence costing. The example below will set those custom attributes if interrogation can extract them from the file. But even if it cannot, it will reference those custom attributes so that costing will calculate after manually inputting them on the part.

```
units_in()
lathe = analyze_lathe()
od = lathe.stock_radius * 2

if od:
    set_custom_attribute('outer_diameter', od)

if lathe.stock_length:
    set_custom_attribute('part_length', lathe.stock_length)

pi = 3.1415926535
expansion_factor = 1.2
od = get_custom_attribute('outer_diameter', 0)
stock_od = od * expansion_factor
removal_rate = 3 # cu in per min
length = get_custom_attribute('part_length', 0)
vol_removal = (pi * (stock_od / 2)**2 - pi * (od / 2)**2) * length

runtime = var('runtime', 0, '', number, frozen=False)
runtime.update(vol_removal / removal_rate / 60)
runtime.freeze()

COST = runtime * part.qty * 50
DAYS = 3
```

You can set default custom part attributes in the settings page. Moving forward, the default attributes you create in the settings page will get copied over to every created part. When you edit, create, or remove the custom part attributes on an individual part, those changes will have no effect on the default custom attributes in the settings page.

Custom part attributes can also be used with custom processes to dynamically generate operations based on the attribute values. Check out our article on custom processes for more information and examples to start from.
