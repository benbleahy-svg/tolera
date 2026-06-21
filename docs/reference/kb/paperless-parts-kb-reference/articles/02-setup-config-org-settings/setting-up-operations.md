---
title: "Setting up operations"
slug: setting-up-operations
source: https://help.paperlessparts.com/s/article/setting-up-operations
topic: "Setup, Config & Org Settings"
captured: 2026-06-19
---

# Setting up operations

> Source: https://help.paperlessparts.com/s/article/setting-up-operations  
> Topic: Setup, Config & Org Settings

Operations capture the manufacturing steps needed to create the parts you are quoting. They are fully customizable, allowing you to leverage the geometric interrogation of the Paperless Parts Platform while combining them with the variables your job shop uses to price specific operations.

**Where are they used?** Operations are used in your processes to create a template that is pre-loaded when a process is selected while drafting a quote.

## Creating an Operation

Navigate to "Configure" and click on the "Operations" tab, or [click here](https://app.paperlessparts.com/processes/operations) when you are logged in. You will see all of your operations listed here. To add an operation, click on the "+ New Operation" button.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d1c040804286369ad8d0e17/file-199zPK7YCt.png)Name your operation first. Choose Operation Category: "Operation" or "Material". Material operations will be tagged.

Then for Operation Type, you will use "Without Machine" for most operations.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/615751eb12c07c18afdd9a0b/file-q7evn4ZKGL.png)

To add a formula to your operation, go to the operation table and click on an operation.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d1c040804286369ad8d0e17/file-199zPK7YCt.png)Then click on "Edit Pricing Formula" to start adding formulas to your pricing.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/615b05a112c07c18afdda16e/file-H7AHEpD3Dq.png)In this Pricing Formula modal, you can specify the formula for your price and lead times using the variables PRICE and DAYS respectively.

For the full documentation of how the pricing formula works, [see this guide](https://api.paperlessparts.com/docs/v2/modules/overview.html#).

### Setting Up an Example Milling Operation

For this example milling operation, we will make the following assumptions to write the formula for the operation:

- Let's assume you price based on shop rate of $75.
- We will use the runtime from the geometric interrogation from the Paperless Parts platform based on the part being quoted
- We will have a default setup time of 1 hour per setup
- We will assume that this operation adds 1 day to your lead time.

1. Declare the shop rate variable like this:

```
 shop_rate = var('Shop Rate', 1, '$ / hr', currency)
```

2. Pre-fill setup time with 1 hr by declaring the setup_time variable.:

```
 setup_time = var('setup_time', 1, 'hr', number)
```

3. We will then call the analyze_mill3() function to use the results of the geometric interrogation done on the part:

```
 cnc = analyze_mill3()
```

4. We will then calculate price as the following formula:

PRICE = shop rate √ó runtime √ó quantity + shop rate √ó setup time √ó number of setups

Type this into the formula as:

```
 PRICE = shop_rate * cnc.runtime * part.qty + shop_rate *setup_time*cnc.setup_count
```

5. To account for the additional lead time for this operation, add:

```
 lead_time = var('Lead Time', 1, '', number) DAYS = lead_time
```

By the end of setting up your formulas for your milling operation, it will look like the following:

```
 shop_rate = var('Shop Rate', 1, '$ / hr', currency)  setup_time = var('setup_time', 1, 'hr', number)  cnc = analyze_mill3()  lead_time = var('Lead Time', 1, '', number)  PRICE = shop_rate * cnc.runtime * part.qty + shop_rate *setup_time*cnc.setup_count  DAYS = lead_time
```

And that's it. Save the formula and start using your operation.
