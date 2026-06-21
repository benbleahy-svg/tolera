---
title: "Discounts P3L cheat sheet"
slug: discounts-p3l-cheat-sheet
source: https://help.paperlessparts.com/s/article/discounts-p3l-cheat-sheet
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Discounts P3L cheat sheet

> Source: https://help.paperlessparts.com/s/article/discounts-p3l-cheat-sheet  
> Topic: Pricing, Costing & P3L

## Discounts P3L Cheat Sheet

Discounting is a commercial strategy to increase revenue by increasing the incentive to buy. In Paperless, discounts are **deductions from the calculated price****(costs + markups + expedites)****of a quote item**.

*Discounted unit price = rounded unit price * (1 - total discount % / 100)*

When discounts are added to a quote item:

- Unit price * quantity will always equal the total price, both before and after discounts
- Total price will always be rounded to two decimal places
- Both the pre- and post-discounts unit price will be displayed on the quote to the buyer
- Add-ons are applied after discounts

Learn more about discounts in Paperless Parts [here](https://help.paperlessparts.com/article/413-discounts).

A discount item is responsible for outputting a numeric percentage value to deduct from the calculated price, after markups and margins are applied. For more information about how markups and margins are calculated, see [here](https://help.paperlessparts.com/article/337-profit-items-p3l-cheat-sheet). Each discount item should set an output percentage using `PERCENTAGE = 10`. The output should always be *positive*, even though the percentage will be used to reduce the price.

Like pricing items, discount formulas have access to the full suite of variable functionality, including `var`, `drop_down_var`, `table_var`, `variable_group`, and `table_lookup`. It also has access to all globally available math functions, such as `mean` and `median`, list functionality, workpiece and price dict (limited to pricing item communication only), access to quantity information with `get_quantities()` and `get_make_quantities()`, and the ability to rename pricing items with `set_discount_name(string)`.

## Global Objects

- contact - global object containing attributes about the contact & account associated on the quote. Same attributes as with operation P3L.
- REQUESTED_QUANTITY - customer requested quantity

## Global Functions

NOTE: We are only including functions that are *not* included in operation P3L.

`set_discount_name(name: str)`

Will dynamically rename the discount item based on the string name argument. If this function is not called, the name will default to the name of the operation definition in your processes page.

## Not Available

Discounts P3L does NOT have access to a lot of operation P3L functionality. This includes: - The `part` object - Custom attributes with `set_custom_attribute` and `get_custom_attribute` - Requesting interrogations e.g. `analyze_mill3()` - Accessing child info with `get_child_info()`

## Basic Example

Use this formula to offer one customer a discount:

```
customer_discount = var('Customer Discount', 0, '', number, frozen=False)
if contact:
	if contact.account.name == 'Best Customer Ever':
		customer_discount.update(15)
else:
	customer_discount.update(0)
customer_discount.freeze()

PERCENTAGE = customer_discount
```

Use this formula with a [custom table](https://help.paperlessparts.com/article/126-custom-tables) called "account_discount_table" to offer discounts for multiple customers:

```
row = table_var(
	'Discount %',
	'',
	'account_discount_table',
	create_filter(
		filter('account_name', '=', contact.account.name)
	),
	create_order_by('discount_percentage'),
	'discount',
)
if contact.account and row:
   	PERCENTAGE = row.discount_percentage
else:
	PERCENTAGE = 0
```

You could also offer a discount if above a certain quantity is ordered:

```
if REQUESTED_QUANTITY > 100:
	PERCENTAGE = 5
else:
	PERCENTAGE = 0
```
