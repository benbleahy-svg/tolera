---
title: "Add-ons P3L cheat sheet"
slug: add-ons-p3l-cheat-sheet
source: https://help.paperlessparts.com/s/article/add-ons-p3l-cheat-sheet
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Add-ons P3L cheat sheet

> Source: https://help.paperlessparts.com/s/article/add-ons-p3l-cheat-sheet  
> Topic: Pricing, Costing & P3L

Add ons are operation-like items that you can add to quote items that can influence total line item cost without influencing the unit price of a component. Things like non-recurring engineering work or tooling fees can be encapsulated by required add ons, where the buyer must purchase these alongside any quantity of a line item. Things like additional value added services or certifications can be encapsulated using non-required add ons that the user can optionally select at checkout if he or she finds it valuable. You can also use add ons to enforce things like minimum order item prices. Add ons can be templatized in a very similar way to operations. Just like with operations, add ons can be added to process templates, so that when a process is applied to a part, it will automatically generate the add ons specified in the template. Add on level P3L is very similar to operation level P3L, except it has access to a slightly different list of functions. You should read through the [Operation P3L Cheat Sheet](https://help.paperlessparts.com/s/article/operation-p3l-cheat-sheet) before going through this article.

Similar to operations, the purpose of add on P3L is to generate a price for a given add on for each quantity break. Additionally, add on P3L can also dynamically specify if an add on is required or not.

In add on P3L, you have access to all attributes of the `part` object as well as all of the built in python function and operators. You additionally have access to all functions specified in the [Operation P3L Cheat Sheet](https://help.paperlessparts.com/s/article/operation-p3l-cheat-sheet) EXCEPT for the following functions:

- no_quote()
- analyze_mill3()
- analyze_lathe()
- analyze_sheet_metal()
- analyze_wire_edm()
- analyze_casting()
- analyze_additive()
- set_operation_name(name)

Each add on P3L formula should end with a `PRICE =` statement.

There are only two additional functions that add ons P3L provides outside of operation P3L:

`set_add_on_name(name)`

Set the name of the add on as it would appear in the user interface. If this function is not called, the name will default to the name of the add on definition in your processes page. This function is particularly useful if your add on naming convention depends on part attributes.

**name** is the string you would wish to rename the add on.

`set_is_required(value)`

Sets the add on to be required or not based on the **value**. If you do not use this function, the is_required value will default to the value specified on the add on definition in your processes page.

**key** is a Boolean.

### Accessing Surrounding Prices

Similar to operation P3L where you can access the cost of surrounding operations, you can access the price of surrounding add ons using a similar function to `get_cost_value_(key)` called `get_price_value(key)` function. You can pass it an add on name or add on definition name and it will return the price of all cells that match that name string for the active quantity. Additionally, there are two special keys to collect accumulated values. Using `get_price_value('--required_add_on--')` will return prices of all cells above the active add on for required add ons. Using `get_price_value('--non_required_add_on--')` will similarly return the price of all cells of above the active add on for non required add ons.
