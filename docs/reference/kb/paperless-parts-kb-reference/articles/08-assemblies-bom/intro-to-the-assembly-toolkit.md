---
title: "Intro to the assembly toolkit"
slug: intro-to-the-assembly-toolkit
source: https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Intro to the assembly toolkit

> Source: https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit  
> Topic: Assemblies & BOM

Learn what the assembly label means and what's unique about quoting assembly parts.

#### On this page

- [What is an assembly part?](#h.1m6ps23tz0rr)
- [When should a part be marked as an assembly?](#h.rerqmufjv6n0)
- [Why should I use the assembly label?](#h.eompcuccupez)
- [How do I create an assembly part?](#h.mox47zin42cg)
- [How do I quote an assembly part?](#h.nys9v6p1vafn)

---

# What is an assembly part?

If a part that you're quoting requires you to make and assemble multiple parts, it should be categorized as an assembly part in Paperless Parts. Assembly parts are tagged with a blue A:

![](https://lh4.googleusercontent.com/o9tx_K_pFbWB3pGIeGVaCBP1T-ILZh-X0JV2tz7UyivlYrRFHVu9Wb-nsGwHt7Zr0sgjzzZROr5xF5WIa_qjMdvZDSMuXO9C122Z9jnr5uzUAmqSvP7kRNPbOB21MIXFThkruo7Zlt2UDe-g4ZJt1LY)

# When should a part be marked as an assembly?

A part should be marked an assembly if you need to account for the cost of manufacturing multiple child parts individually and then assembling them together into one ship-level item in order to accurately quote the whole piece.

# Why should I use the assembly label?

Assembly parts have an indented BOM structure, or tree, where you can easily keep track of the costs associated with each child part. You can use this tree and assembly-specific quoting tools to quickly navigate your assembly, keep track of which components you have/haven't quoted, and get an overview of where your costs are coming from.

Similar to assemblies, non-assembly parts have a **Components** section where you can keep track of hardware. This section looks like the **Assembly components**section, but it doesn't have the same level of functionality (which we call the assembly toolkit) since you won't set up a router for each purchased component associated with a part.

# How do I create an assembly part?

There are two ways to create an assembly part in a quote:

1. Upload a CAD file with multiple components.
  1. If you upload a multi-component CAD file while creating a quote item, Paperless Parts will automatically mark the part as an assembly and extract the structure of the part to create a tree (as drawn/created by the design engineer).
2. Mark an existing part as an assembly with the **Make assembly** action.
  1. Without a 3D model, there's no way for Paperless Parts to tell how many components a part has. For this reason, PDF parts and manual parts will never automatically be marked as an assembly on upload.
  2. To tag a quote item as an assembly, click the three dots next to the quote item in the navigation bar and select **Make assembly**. ![](https://lh3.googleusercontent.com/RC8telj9sSbKERG611Ov2hSPCePZMfPM9iUIQuAsnnGNQ8pLvVzJGF974uQmcjuys6Dl3uN7halhX_iXzarRsuuuyIMayHSK8KqeSL45kcvPA2KjRvvVImxs0t9d6o_iXfzYIBkdGVAFMBcbJXuW4nA)

# How do I quote an assembly part?

Just like non-assembly parts, you'll use processes, operations, and pricing items to arrive at a price when quoting an assembly part. Unlike non-assembly parts, you'll need to know where in the assembly structure to assign these items.

Putting costs in the "wrong" place won't break your quote, but some operations will calculate cost differently depending on where they're located in a tree structure. Being intentional about where you cost in the assembly tree will help you maximize automation, make fewer overrides, and get quotes turned around in less time. If you have an integration, assigning costs in the "right" place will also ensure that all routing steps in the assembly appear in your ERP system as intended, reducing the need for manual BOM manipulation in your ERP.

Because a part's costing is impacted by its tree, make sure that your assembly part's BOM structure is finalized before you start to assign processes or add operations.

A few ground rules for quoting assembly parts:

1. Confirm the BOM structure *before* you start costing.
  1. This process will be a little different depending on if the part's primary file is a 3D model or a PDF, but at a high level, always make sure you're starting with the correct hierarchy and labeling (i.e. manufactured vs. purchased) of all child parts in the BOM.
2. In general, don't assign material or machining costs to the upper level of any part marked as an assembly - only to non-assembly child parts.
  1. Costing for child components should reflect how much it will cost to make that specific part in your shop (such as raw material and machine time) while the top level part should only have costs that apply to the entire assembly part (such as assembling, shipping, or inspection time).
3. Use the navigation bar to stay oriented while you quote.
  1. Because there are multiple places to add costs in the BOM structure, make sure you're always working in the right spot. Scrolling too far up or down in the quote item can land you in the wrong part. Use the tree in the navigation drawer and the blue component bar at the top of your quote to keep track of where you are assigning costs.
4. Pricing only occurs at the top level of an assembly quote item.
  1. Costing items, like processes and operations, can be assigned to the top level of the assembly or to individual components.
  2. Pricing items, like markups and margins, cannot be assigned to child components.

#### For a detailed walkthrough of quoting an assembly part, check out our article on [Quoting an assembly part from a model](https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-model?preview=6418689b4627a93f4d0e7325).
