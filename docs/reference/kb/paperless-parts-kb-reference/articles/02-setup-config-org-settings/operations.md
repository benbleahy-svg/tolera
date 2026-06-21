---
title: "Operations"
slug: operations
source: https://help.paperlessparts.com/s/article/operations
topic: "Setup, Config & Org Settings"
captured: 2026-06-19
---

# Operations

> Source: https://help.paperlessparts.com/s/article/operations  
> Topic: Setup, Config & Org Settings

Learn about the role operations play in quoting and how to configure them.

#### On this page

- What is an operation?
- How do I set up an operation?
  - Creating a new operation
  - Configuring an operation

---

# What is an operation?

An operation is a specific item, step, or task within the manufacturing process that contributes to the cost of a part. You can think of an operation sort of like a work center or a spreadsheet macro, but with more visibility and potential for automation.

In a quote, operations act as router steps. From the Build-a-Quote page, you can view an operation's name, cost, and unit cost. Some operations also display the setup and run time. ![](https://lh5.googleusercontent.com/wpwTtNFYLSl0h0Qt1k0Hp4D7mSVN6vwVTY6j3e7d4ekKc5QtW_KwB7UhPSihizWWjmxjSYgh8IND1hP9CkXcysD9yUOU1DlHmfY300B6dbt1SutUVh5GKPNnXWTafUq1tWPMuwQmqQVWUW9w9U0fo7Q)

1. Name: The description of the operation.
2. Setup Time: The amount of time it takes to set up the machine for this routing step. (Not available for Material operations.)
3. Run Time: The amount of time it takes to perform this step for an individual part. (Not available for Material.)
4. Operation cost: The cost of performing this routing step to deliver the customer-requested quantity.
5. Unit cost: The cost per part of performing this routing step to deliver the customer-requested quantity.

Most basic operations will multiply setup and run time by an hourly rate to calculate a unit and operation cost. More complex operations calculate cost from a wide range of variables, such as a part's atomic material, geometry, costing variables, custom attributes, etc. An operation's complexity and properties (like its name, variables, and calculations) are configurable and account-specific.

In the Build-a-Quote page, operations are split into two categories: **Material** and **Operations**. Operations in the material section capture required material costs, such as workpieces, while generic operations typically account for a manufacturing step or task that occurs in your shop.

# How do I set up an operation?

You can view and configure your shop's operations from the Operations tab of the Configure page. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6410bd8fcde2720700022c2f/file-1CxW2ruCpX.png)

Select an operation to view its inputs, or click **+New operation** at the bottom of the tab to add an operation.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6410d2593387cb3e147b7910/file-9AnAQ8tbKD.png)

Once you've clicked **+New operation**, you'll need to fill out some information about your new operation.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6410d3cbc79fa516eb24879f/file-oSYjsWRdAn.png)

1. Operation name
2. Operation category: Will this operation account for required material costs? If so, select "Material". Otherwise, leave it as "Operation".
3. Outside service: Will this step be performed outside of your shop? If so, toggle Outside service to on.
4. Operation type: Here, you can select a machine to associate with the operation. This is primarily useful for additive shops.

Select **Create operation**to confirm.

## Configuring an operation

Select an operation to open it.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/647f69187f8c2575e354468b/file-N8tkHvqY6a.png)

1. Operation name
2. Setup time display units: Should the setup time be displayed in hours, minutes, or seconds on the build-a-quote page?
3. Operation category: Select "material" if this operation is accounting for material costs. Category determines where the operation appears on the build-a-quote page.
4. Runtime display units: Should the runtime be displayed in hours, minutes, or seconds on the build-a-quote page?
5. Is outside service: Will this step be performed outside of your shop? If so, toggle Outside service to on.
6. ERP code: If your shop has an ERP integration that imports workcenters, this field may be used to map operations in Paperless Parts to workcenters in your ERP.
7. Costing inputs: This section includes a list of the variables used to calculate cost for this operation and their default values. All of these variables are defined in the operation's P3L, which you can view by clicking Edit operation formula.
  1. To change a variable's default value, click into the box next to its name and type a new value.
  2. Deselect a costing input to remove it from the list of variables. The variable will still be accessible from the P3L, but you'll need to edit the operation formula to change its default value.
8. Edit operation formula: Click here to open the P3L editor for this operation.
  1. Learn more about P3L here.
9. Duplicate and Delete: Either duplicate or delete the entire operation.
