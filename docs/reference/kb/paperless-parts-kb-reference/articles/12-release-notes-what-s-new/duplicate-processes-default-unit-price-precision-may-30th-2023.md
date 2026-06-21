---
title: "Duplicate processes, default unit price precision - May 30th, 2023"
slug: duplicate-processes-default-unit-price-precision-may-30th-2023
source: https://help.paperlessparts.com/s/article/duplicate-processes-default-unit-price-precision-may-30th-2023
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Duplicate processes, default unit price precision - May 30th, 2023

> Source: https://help.paperlessparts.com/s/article/duplicate-processes-default-unit-price-precision-may-30th-2023  
> Topic: Release Notes (What's New)

We're closing out May with two releases that will make [processes](https://help.paperlessparts.com/s/article/processes) more impactful and easier to set up in your Paperless Parts account.

- Duplicate processes action
- Default unit price precision for processes

# Duplicate processes

You can now use the **Duplicate process** option to create a new process without starting from scratch.

To duplicate a process, open the process from the [Processes tab](https://app.paperlessparts.com/processes) of the Configure page. Scroll to the bottom and select **Duplicate**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/646fb11c06d1de0f8f3de860/file-uGOJddPCcx.gif)

This will create a new process with an identical configuration to the original, including:

- The internal and displayed process name
- The custom process formula (if applicable)
- Standard lead time and yield
- Default unit price precision
- Material list
- Operations, finishes, add-ons, pricing items, and discounts
- SmartRFQ display settings

This function can be especially useful if you're creating a custom process and want to use the same operation generation logic as an existing process.

# Default unit price precision

If your shop does stamping or another form of high-volume work, you may find yourself regularly changing the [unit price precision](https://help.paperlessparts.com/s/article/pricing-a-part#precision) on quote items to communicate a more precise price to your buyer. With this release, you can now set a default unit price precision for each process in your account.

To adjust a process's unit price precision, open the process from the Configure page. Select the unit price precision (2, 3, or 4 decimal places) that should be the default for any quote items assigned that process.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/646fb2cc67106052aab4ca33/file-mEP2Enqxl7.png)

By default, new processes will have a unit price precision of two decimal places.

*Note:* Adjusting a process's default unit price precision will **not**affect existing quote items with that process assigned (including outstanding quotes). Any changes you make to default precision will only apply to future quote items you assign that process to.

You are still able to change the unit price precision on individual quote items from the pricing table:

![](/servlet/rtaImage?eid=ka05G000000uq0V&feoid=00N5G00000WB8Hk&refid=0EM5G00000DIxo0)

The unit price precision dictates how the final unit price will be displayed on the Digital Quote or Quote PDF to your buyer:

![](/servlet/rtaImage?eid=ka05G000000uq0V&feoid=00N5G00000WB8Hk&refid=0EM5G00000DIxo1)

Changing the unit price precision does not affect the calculations done to reach the final unit price (calculation steps are never rounded, the only time rounding occurs is when determining the unit and total price). The total price will always be rounded to the nearest cent, and *unit price x quantity* will always be equal to the total price.
