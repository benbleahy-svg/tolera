---
title: "Costing a part"
slug: costing-a-part
source: https://help.paperlessparts.com/s/article/costing-a-part
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Costing a part

> Source: https://help.paperlessparts.com/s/article/costing-a-part  
> Topic: Pricing, Costing & P3L

Learn how to use operations to estimate the cost of a part.

#### On this page

- Setting up your router
  - Adding removing, and reorganizing operations
- Reviewing and adjusting costs
  - Overriding costs
  - Adjusting costing variables
- Make quantity and yield
- Hardware
- Reviewing costs in the costing table
- FAQ

---

# Setting up your router

Below the Process section, there are two sections that store all of the costs associated with your part: Materials and Operations. Each individual cost that you accrue while making a part will be calculated in an operation and stored in one of these sections.

![](https://lh4.googleusercontent.com/3kAJFyGJq_p-aGuNP1g3TYv8B2HnCVMSDsMDKs9EJ4PvY20uYcM-Bg8bLj-vVuhUdFHIpF58NhPrf0O2wDFKIH5KiOqX3rAbTQl3LNzNE4xNlNJxWFSZkfyvOZHpJZFmuqo0aUijiDutwS_3mEZgiq0)

- The Materials section contains required materials costs. Each operation in this section should account for the cost of a raw material workpiece required to make the part.
- Operations in the Operations section account for other costs such as labor, machine time, and outside services.

*Tip*: Individual operations will not be listed on the final quote. If you need a customer to see a cost, try using an add-on instead of an operation.

## Adding, removing, and reorganizing operations

First, confirm that the list of operations accurately reflects how you'll manufacture the part.

To add an additional material cost, click **Add material operation** in the Materials section. Select the material operation you would like to add or narrow down your search by typing.

![](https://lh5.googleusercontent.com/2ljDc9OkEyXI8qy9hMX4dCSgOpeuVIKtAJeoRiwhDQNVdver9K6KG83SXRTeVwIJCN9Y0NQoG6u6bEt4IFvKz24VyjSlDBBJNvbwKGlYCQphKcEh6PgR2-fVQZ8CeyHdixEVBdfIRNn47CliI7-pF6Q)

Similarly, to add an additional inside or outside processing cost, click **Add operation** in the Operations section.

To change the order of an operation in the router, click and drag the three lines to the left of the operation name.

![](https://lh4.googleusercontent.com/u9sOl8fIscgA6XLJmPmZkNohKaBpQfSB1UDoPc2__47IAqZimpJbMBUwymbAhvKNDQ9UBE49ekFEuFnZjxMcUNF5XUAVqhaEUsN8RUYuyRzzpbtofY6KNvr9JVirq8TibdIUwm-gzZ0idD7svV1Jw3k)

To remove an operation, click the trash can symbol to the right of the operation's name.

![](https://lh5.googleusercontent.com/PMGojXisJajLBpIYt4wzvGgAoWe2QW5bYpr-9AmFiN6Pf_aBvE0YxGZfjmN1GSg7swwGRqbPqhloFscMy9LPH4PzaZJ25dMVluqosE6D4fQnx0HVxPyqr28y35TT1W7xA-WGsuR6wr0p8hr7gtQbBr0)

# Reviewing and adjusting costs

Once you're satisfied with your router, the next step is to review and finalize costs. Each operation will display the following values:

![](https://lh6.googleusercontent.com/WR__yJPTKI9jUwQGTmOAUjDAOjryhOMqONuFD28QiWNuLQ01Xl0R0YcFlhV8ZGB-lCp6RJPPVnHsGtnNiVm7rPKfdFWqNn-Ev-laMMIjNPUQWAfOCYWrGn7xWCPKflwvLv25Zu8G_fxfrSa8CusrbQc)

1. Name: The description of the operation.
2. Setup Time: The amount of time it takes to set up the machine for this routing step. (Not available in the Materials section.)
3. Run Time: The amount of time it takes to perform this step for an individual part. (Not available in the Materials section.)
4. Operation cost: The cost of performing this routing step to deliver the customer-requested quantity.
5. Unit cost: The cost per part of performing this routing step to deliver the customer-requested quantity.

Most operations will have defaults so that they have a non-zero cost value as soon as they are assigned to a part. In the presence of a CAD file, they may also be calculating a cost based on the part's geometry. For that reason, when you start quoting you should primarily be *adjusting* costs instead of adding them, either by:

1. Overriding an operation's cost from the router.
  1. This is the fastest way to adjust cost and is best used when an operation's cost is either coming from a default value or a very simple calculation.
2. Opening an operation and overriding the variables it uses to calculate a cost.
  1. This is the most precise way to adjust cost and is best for when an operation is performing a more complex cost calculation.

## Overriding costs

Any value listed in blue in a quote item (including the operation cost and total quote item cost) can be overridden by selecting it, typing a new value, and pressing ENTER.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/640f8bdadc01bb231eb3c3f2/file-b5XWbC3wbA.gif)

This can be especially useful when you're adjusting an operation with a simple cost calculation, or a default value/lot charge. In this case, for instance, "Programming (Milling)" is simply setup time multiplied by an hourly rate.

Any value that has been overridden will be yellow with a black arrow next to it. Hover over the arrow to see who performed the override, when, and what the initial calculated value was.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/640f8cb5cde2720700022b01/file-EaEcrjz7Gx.png)

## Changing costing variables

If you're editing an operation with a more complex cost calculation, you can precisely fine-tune an operation by adjusting the variables it uses to calculate cost.

To view an operation's variables, click the two arrows next to its name.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/640f8ee167d5242b940eee82/file-KFeiizHSWM.png)![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/640f8efa3387cb3e147b77e9/file-iow27EhmDy.png)

For instance, this "Bar pricing" operation is calculating cost based on the size of the part, the size of the material stock, and a cost per pound value for the raw material. Rather than overriding the entire operation cost, we can override the "Cost per pound" variable to change the total cost of this required material. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/640f8fa167d5242b940eee86/file-j1uX99NgAv.gif)

# Make quantity and yield

By default, most operations perform their calculations based on the make quantity of a part rather than the customer-requested quantity. When yield is 100%, these values are the same.

You can adjust a part's make quantity by changing the yield (listed directly above make quantity).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6411d28ab312a07720797a31/file-bOh5IJWcwD.gif)

# Hardware

The final costing section on the Build-a-Quote page is **Components**,where you can account for any hardware you'll be adding to a part.

If you're quoting a part with hardware off of a CAD file, the part may have automatically been tagged as an assembly part, in which case you'll need to convert it to a part with hardware. Learn more about assembly parts and this process [here](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part#h.siojoselme4m).

Otherwise, you can add hardware directly to a part by clicking **Add components to top level**and selecting **Add purchased component**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6411d8f5b312a07720797a44/file-7RtJoRzSXO.png)From there, browse your [purchased component library](https://help.paperlessparts.com/s/article/purchased-components) to select an existing purchased component in your account or create a new one.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6411d9e062419b2ed486b974/file-tCShkkzkbW.png)

Once you confirm your selection, the hardware cost will be included in the final price of the quote item.

# Reviewing costs in the costing table

Scroll down to the [Costing table](https://help.paperlessparts.com/s/article/costing-table) to review the total cost of a part. Each row details a different category of cost, or "color of money", as signified by its badge.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6411dad08516b6333a8388d7/file-Wxa7v7hQ2K.png)

- Total Raw Material = the sum of all material operations
- Total Inside Processing = the sum of all operations not marked as an outside service
- Total Outside Processing = the sum of all operations marked as an outside service
- Total Purchased Components = the sum of all total costs associated of purchased components (including overrides to a purchased component's unit cost)
  - Note: This row will not appear if the quote item has a single component (not an assembly)
- Total Manufactured Component Overrides = the difference between the total estimated cost and the sum of all colors of money
  - Note: This row is necessary because you can specify a manual unit cost for manufactured components within an assembly. If you manually override this value, we lose the ability to rigorously break down your costs into different colors of money. As a result, we recommend that you do NOT manually override unit cost for child components, and instead modify costs within operations.
  - Note: This row will not appear if the quote item has a single component (not an assembly)

These cost categories are not only important immediately in a quote item, giving you insight into where you're acquiring costs *before* you send your buyer a final price, but they also drive profit margins and can be referenced by the analytics tool.

*Tip:*Click the gear icon in the top right to see these costs out to four decimal places or view them as a percent of total cost rather than a dollar value.

#### Once you're satisfied with the cost of the quote item, the next step is to add pricing.

# FAQ

## How can I see more decimals in an operation's cost?

To view operation cost out to four decimal places, click the gear icon in the top right corner of the Operations section to open Display options.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6410b8f1dc01bb231eb3c4ed/file-UWanF744Lp.png)Deselect **Truncate values**and click apply.![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6410b91267d5242b940eef9b/file-YuUsoZ60wr.png)
