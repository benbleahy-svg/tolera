---
title: "Drop down variables"
slug: drop-down-variables
source: https://help.paperlessparts.com/s/article/drop-down-variables
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Drop down variables

> Source: https://help.paperlessparts.com/s/article/drop-down-variables  
> Topic: Pricing, Costing & P3L

Drop down variables are a P3L variable type that allow you to specify a discrete list of options that a variable value can be. When overriding this variable at quote time in the live pricing preview, you can only choose from the discrete options you have given the drop down variable from within your P3L formula. Here is what a drop down variable looks like in the quoting interface.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5fad2dd5cff47e00160b9330/file-MwPQvH1bYo.png)

**HINT:**You can search for values in the drop down by typing in the input box!

Drop down variables can concisely drive logic in pricing formulas while requiring minimal training and input for operators. You can use drop down variables to navigate "logic switches". A "logic switch" describes a situation where an input will determine which behavior will occur from a discrete list of options (e.g. if the drop down value is a, perform logic a, if the value is b, perform logic b). You can assign intuitive names/values to the options of these "logic switches" allowing you to break down complicated pricing formulas into simple discrete steps. Drop down variables simplify training and operator input by increasing clarity of pricing logic.

Drop down variables inherit and extend the dynamic functionality of standard variables. Drop down variable options and also the selected value can be dynamically updated based on upstream pricing logic from within P3L. Drop down variables work great for simply logic switches, but also can be used for involved custom form logic that depend on multiple layers of inputs.

## Cheat Sheet

#### Creation Function

`drop_down_var(name: str, default_value: str, default_options: P3LList, description: str, value_type: str, frozen: bool = True, quantity_specific: bool = False) -> DropDownVariable`

Create a new `DropDownVariable` instance. The **name** must be string unique to this variable across all variable types (`var`, `table_var`, and `drop_down_var`). The **value_type** matches the **value_type** input for the standard `var` function and can either be `number`, `currency`, or `string`. If `number` or `currency` is specified, the **default_value**, **default_options**, and any options or values added/selected downstream will be casted to an integer or float (depending on if the input is an integer or not). If `string` is specified, all of these will be casted as a string. The **default_value** is the value that will by default be selected for the drop down variable. This value must be castable to the specified **value_type**. You can specify things like dynamic `var` objects to this input. The **default_options** are a P3LList of values that must be castable to the typing specified by **value_type**. The **default_options** can consist of simple string and number inputs, but can also be dynamic `var` variables as well. If the **default_value** is not found within the **default_options**, it will be automatically added to the **default_options** P3LList within the instance. There cannot be more than 50 options. If more than 50 are specified, the array will be truncated to the first 50 entries. If you need more entries, contact support. The **description** is a string describing the purpose of the variable. **frozen** is a True/False input that dictates whether the options and/or value of the drop down variable can be updated after declaration. **quantity_specific** is True/False input that indicates whether the variable appears for individual quantity breaks in the live pricing UI. Check out our article on [quantity-specific variables](https://help.paperlessparts.com/s/article/quantity-specific-variables) for more information. Any overrides applied to the drop down variable from the operation or add on live pricing interface will take affect *at the time the variable is frozen in the pricing program*.

**NOTE:**`drop_down_var` cannot be called inside a conditional (if/elif/else) or a for loop.

#### Properties

A `DropDownVariable` has two properties that you can access via "dot" notation. Let's assume we have initialized a drop down variable using the `drop_down_var` function as `ddv`:

| **Property** | **Description** |
| --- | --- |
| `ddv.value` | Returns float, integer, or string of the currently selected value (depending on `value_type` of `DropDownVariable`) |
| `ddv.options` | Returns a `P3LList` copy of the current options of the `DropDownVariable` casted to float, integer, or string values (depending on `value_type` of `DropDownVariable`) |

#### Methods

All of these methods apply to dynamic drop down variables, or variables created with `frozen=False`. Before utilizing these methods, particularly the manipulation of options, we recommend you familiarize yourself with P3LList objects. These are all used via "dot notation" on a `DropDownVariable` instance declared using the `drop_down_var` function. The variable must not yet be frozen to perform any of the following methods. If you attempt to perform any of these methods on a frozen variable, the program will throw an error. Additionally, any methods that require an input will be casted to the proper typing dictated by the `value_type` of the drop down variable. If the input cannot be successfully cast to the proper typing, the program will throw an error.

**NOTE**: Number of options can not exceed 50. If options already are of length 50, methods will not add any new options.

`select_option(option, force=False)`

Selects the inputted **option** as the value for the drop down variable. If `force=False` and the **option** is not present in the drop down variable options, an error will be thrown. If `force=True`, the value will be set to **option** regardless if **option** is currently in the list of options for the variable and **option** will be added to the list of options if it is not already present.

Calling this method will freeze the variable. This means that you will not be able to manipulate the value or options after calling this method. Any overrides applied in the live pricing interface will take affect when calling this method.

`select_default()`

Sets the **default_value** specified for the drop down variable to the value.

Calling this method will freeze the variable. This means that you will not be able to manipulate the value or options after calling this method. Any overrides applied in the live pricing interface will take affect when calling this method.

`select_option_or_default(option)`

Selects the inputted **option** as the value for the drop down variable if it is present in the options of the variable. If **option** is not present in the drop down variable options, the **default_value** will be selected as the value.

Calling this method will freeze the variable. This means that you will not be able to manipulate the value or options after calling this method. Any overrides applied in the live pricing interface will take affect when calling this method.

`append_option(option)`

Appends **option** to the options of the drop down variable. This WILL NOT check if **option** already appears in the options list.

`extend_options(options: P3LList)`

Extends **options** to the options of the drop down variable. This WILL NOT check if any option within **options** already appears in the list.

`add_option(option)`

Appends **option** to the options of the drop down variable ONLY IF **option** does not already appear in the options list of the variable.

`update_options(options: P3LList)`

Extends **options** to the options of the drop down variable that are not already found in the options list.

`reverse_options()`

Reverses options list.

`clear_options()`

Clears options list. Sets it to an empty list.

`remove_option(option)`

Removes **option** from list of options if **option** is present in the list. Will only remove the first instance this appears.

`sort_options(lambda_func)`

Sorts the options list based on the lambda function, e.g. `ddv.sort_options(lambda x: -x)`. Check out article on [P3L Lists](https://help.paperlessparts.com/s/article/p3l-lists) for more information on how to use this.

`filter_options(lambda_func)`

Filters the options list based on lambda function, e.g. `ddv.filter_options(lambda x: x > 10)`. Check out the article on [P3L Lists](https://help.paperlessparts.com/s/article/p3l-lists) for more information on how to use this.

## Usage

```
# create a simple, non-dynamic drop down variable
ddv = drop_down_var('Test Var', 'a', create_list('a', 'b', 'c'), 'Sample drop down var', string)
ddv.value  # 'a'
ddv.options  # ['a', 'b', 'c']

# create a simple, non-dynamic drop down variable with numbers
ddv = drop_down_var('Test Var', 1, create_list(1, 2, 3), 'Sample drop down var', number)
ddv.value  # 1
ddv.options  # [1, 2, 3]

# create a drop down variable without specifying options
ddv = drop_down_var('Test', 1, create_list(), 'Sample drop down var', number)
ddv.value  # 1
ddv.options  # [1]

# create a drop down variable with upstream specified variables
v1 = var('Input Var', 0, '', number, frozen=False)
v1.update(3)
v1.freeze()
ddv = drop_down_var('Test', v1, create_list(1, 2, v1, 4), '', number)
ddv.value  # 3
ddv.options  # [1, 2, 3, 4]

# create a dynamic drop down variable
ddv = drop_down_var('Test Var', 'a', create_list('a', 'b', 'c'), '', string, frozen=False)
# append option
ddv.append_option('d')
ddv.options  # ['a', 'b', 'c', d']
# extend options
ddv.extend_options(create_list('d', 'e'))
ddv.options  # ['a', 'b', 'c', 'd', 'd', 'e']
# remove option, only removes first instance
ddv.remove_option('d')
ddv.options  # ['a', 'b', 'c', 'd', 'e']
# add option, will only add if option not in the options list
ddv.add_option('e')
ddv.options  # ['a', 'b', 'c', 'd', 'e']
ddv.add_option('f')
ddv.options  # ['a', 'b', 'c', 'd', 'e', 'f']
# update options, only adds them if not present
ddv.update_options(create_list('f', 'g'))
ddv.options  # ['a', 'b', 'c', 'd', 'e', 'f', 'g']
# reverse options
ddv.reverse_options()
ddv.options  # ['g', 'f', 'e', 'd', 'c', 'b', 'a']
# filter options
ddv.filter_options(lambda x: x < 'e')
ddv.options  # ['d', 'c', 'b', 'a']
# sort options
ddv.sort_options(lambda x: x)
ddv.options  # ['a', 'b', 'c', 'd']
# clear options
ddv.clear_options()
ddv.options  # []

ddv = drop_down_var('Test Var', 'a', create_list('a', 'b', 'c'), '', string, frozen=False)
ddv.select_option('b')
ddv.value  # 'b'

ddv = drop_down_var('Test Var', 'a', create_list('a', 'b', 'c'), '', string, frozen=False)
ddv.select_option('d', force=True)
ddv.value  # 'd'
ddv.options  # ['a', 'b', 'c', 'd']

ddv = drop_down_var('Test Var', 'a', create_list('a', 'b', 'c'), '', string, frozen=False)
ddv.select_option_or_default('d')
ddv.value  # 'a'
```

The usage cheat sheet above demonstrates how you would use each method and call each property. Depending on your application, drop down variables can be extended to create more complex and dynamic form inputs that can respond to things like part material, geometry, or customer. Using dynamic variables and custom tables, it is possible to implement custom routing of operation logic while maintaining minimal training overhead for the estimating team. Check out the article on [custom tables](https://help.paperlessparts.com/s/article/custom-tables) to see how this works.
