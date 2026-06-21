---
title: "Processes"
slug: processes
source: https://help.paperlessparts.com/s/article/processes
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Processes

> Source: https://help.paperlessparts.com/s/article/processes  
> Topic: Part Analysis & Interrogation

Learn about the role processes play in quoting and how to configure them.

#### On this page

- What is a process?
  - What is a custom process?
  - What is a CNC process?
- How do I assign a process to a quote item?
  - How do I change a quote item's process?
- How do I set up a process?
  - Creating a new process
  - Configuring a process
- FAQ

---

# What is a process?

A process is an estimating template that can be quickly selected and applied to a quote item. Each process has a default set of operations, pricing items, add-ons, discounts, lead times, and more, all of which will be added to a quote item when a process is first assigned. You can configure a process template from the Configure tab at any time.

Typically, a process's name will reflect how you'll manufacture the part in your shop ("CNC Mill 5-axis", "Laser", etc.). This makes it easier to select the correct process and also lets your buyer know how you'll generally be making the part, as the process name is displayed on the finalized quote (depending on your [account settings](#visible)). That being said, process names are highly customizable and can be anything from "Jim's process" to "Complex waterjet" - what's most important is that they are easy for your team to select and assign while quoting.

## What is a custom process?

Custom processes are processes with rules that drive the automatic selection of router steps. Those rules are [dictated by P3L](https://help.paperlessparts.com/s/article/custom-operation-generation) and typically use a part's geometry to determine which operations will be assigned to a quote item.

For example, let's say you're quoting two parts with CAD files - a flat part and a part with a bend - both of which you'll be lasering out of a sheet of material. You assign the same custom process ("Laser") to each. Both parts end up with the same base set of operations, but the bent part has an additional "Press brake" operation that the flat part doesn't. In this scenario, the custom "Laser" process was set up to call a "Press brake" operation in the presence of a bend.

*Note*: This feature is included in the Professional and Enterprise pricing plans.

## What is a CNC process?

Like custom processes, CNC processes will use a part's CAD file to determine which router steps to generate. Specifically, a CNC process will look at the number of setups detected on a part's 3D model and call certain operations once per setup.

For instance, in this CNC process, the milling estimate operation is marked as **Per Setup**. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64079ba8023a35108b661c26/file-ptaPujTfZ5.png)

When we assign this process to a part with two detected setups, the resulting router will automatically assign two CNC Milling estimates operations.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64079c659c8683055bad38dd/file-JtLWsXubcO.png)

These processes can be useful if you want one operation per CNC setup but otherwise have a templated process.

# How do I assign a process to a quote item?

When you first create a new quote item, you'll be prompted to [assign a process, material, and finish](https://help.paperlessparts.com/s/article/assigning-a-process-material-and-finish).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63f53564188a9d242a7d5b01/file-513QBVeVx8.png)Click the arrow next to **Select Process**to browse available processes, optionally typing to search.

Once you've selected the appropriate process, select **Confirm**. This will apply all operations, add-ons, pricing items, and the standard lead time in the process template to the quote item.

*Note:*This selection is not required to create a quote item and can be assigned later from the **Process** section of a quote item.

## How do I change a quote item's process?

*Warning:*Changing a quote item's process late into quoting may cause you to lose existing costing.

To change a quote item's process:

1. Open the quote item and navigate to the Process section.
2. Select Change process.

- Select a new process from the menu, optionally typing to search.
- Click Update to change the process and regenerate all operations.
  1. Note: Changing a process mid-quote will delete all existing costing and pricing items unless you select Update and keep existing ops.
