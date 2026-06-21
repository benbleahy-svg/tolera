---
title: "Quoting an assembly part from a model"
slug: quoting-an-assembly-part-from-a-model
source: https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-model
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Quoting an assembly part from a model

> Source: https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-model  
> Topic: Assemblies & BOM

Learn how to estimate the cost of an assembly part from a model in Paperless Parts.

*Note*: This document is for true assembly parts (multiple manufactured components that are assembled and shipped as a single part). If you're quoting a part with hardware from a model, check out [this article](https://help.paperlessparts.com/s/article/quoting-a-part-with-hardware-from-a-model) instead.

### On this page

- [Quick start guide](#h.df9hlulbh6l6)
- [Written walkthrough](#h.cssy8czcx36)
  - Create the assembly part's quote item
  - [Confirm the BOM structure](#h.xq1obkyxio8b)
  - [Costing](#h.gylncae6tis3)

---

# Quick start guide

1. Upload the CAD file to a quote, ensuring that you have [exported and packaged the file correctly](https://help.paperlessparts.com/s/article/supported-file-types#pack-n-go).
2. Confirm the BOM tree structure, [making adjustments to the quantity and hierarchy](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part) as needed.
  1. Most child parts will initially come in as manufactured parts - convert any child parts that are hardware to purchased components, including child assembly parts (such as hinges).
  2. Replace any subassemblies that should actually be manufactured parts with hardware using the [Replace assembly with manufactured component](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part#h.siojoselme4m) action.
3. Cost all parts in the BOM, marking them "Complete" as you go.
  1. Add raw material and labor costs to all manufactured child parts.
  2. Add assembly and shipment costs to the top-level assembly part.
4. Add pricing items, add-ons, and discounts to the top level of the assembly part.

---

# Written walkthrough

## Create the assembly part's quote item

First, upload the CAD file for your assembly part into a quote to create a new [quote item](https://help.paperlessparts.com/s/article/setting-up-quote-items). To ensure that the file loads correctly, follow our upload instructions [here](https://help.paperlessparts.com/s/article/supported-file-types#pack-n-go).

Once you upload your file, a **Create Line Item** window will appear, prompting you to select the following for your part:

- [Process](https://help.paperlessparts.com/s/article/processes#what)
- Material
- Finish
- Customer-requested quantity
- ITAR status

The selections you make here will only be applied to the top level of the assembly part, not to any of the child parts. With that in mind, be sure to select a process from your library that is meant for quoting parts with children (likely named **Assembly**). (These fields are also optional and can be filled out later in the quoting process.)

Click **Confirm** to create a new line item with your selections.

![](https://lh6.googleusercontent.com/F136GkI9HUSMrtiBdHne6ywSZ7TL3W3nJYIXfWNjI_teng2kzo0-_bJqdG2kT0F3jmtisMNyWYyyCwLvPxw5Le9Z7vd4DTveHa7eOAIPMURA8i84Zv8xlP_JPNsZ5sS9Rt4i39Tv1G97FnOKnQFpCY4)

Select the part in the navigation bar to open the quote item.

Once the quote item is open, you can view the tree structure in the navigation bar underneath the part.

![](https://lh5.googleusercontent.com/sLsmeXHHF0Z4HwAsRBoi4rM_zQgSTxb1aZQlu5xcqlzPLvof389TkzNF-Cq-sH44tLIeE1PBMlQEGqOAHkZWm_J_IFIu113AvnpplfohTzYmM_8_u9hhCypWOLZMdYqpM0ltyxCDYX_ajkZpr1Eihjs)

The icon next to each part in the BOM hierarchy lets you know what type of part it is, which in turn dictates how you'll cost it.

1. Parts with a grid symbol are [assembly parts](https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit#h.1m6ps23tz0rr). Costing items assigned to any part with a grid should detail the cost of assembling its child parts and preparing the final assembled part for shipment.
2. Parts with a cube are single-component **manufactured parts**. Costing items assigned to any part with a cube should detail the raw material and labor costs required to make it, [just like any other non-assembly part](https://help.paperlessparts.com/s/article/costing-a-part).
3. Parts with a hex nut are [purchased components](https://help.paperlessparts.com/s/article/purchased-components), which pull their costing from your purchased component library. Because of this, you should not add costing items to a purchased component.

### Confirm the BOM structure

Before adding any costing or pricing to your assembly part, confirm that the tree extracted from the CAD file is correct.

Because almost all child parts will initially be categorized as manufactured components or subassemblies, the first step is to identify any child parts that are hardware and [convert them to purchased components](https://help.paperlessparts.com/s/article/purchased-components#h.xxur1ljdyucb).

After converting a child part to a purchased component, its cost will be calculated from the piece price in the purchased component library. You should not need to perform any further costing on that part.

Once all hardware is labeled correctly, you can use the following tools to adjust the BOM structure:

1. [Change the BOM quantity of a child part.](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part#h.j5ifomv3p3rx)
2. [Convert subassemblies to parts with hardware.](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part#h.siojoselme4m)
3. [Move a child part up a BOM level.](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part#h.jjb3kthl8gk9)
4. [Move a child part down a BOM level.](https://help.paperlessparts.com/s/article/editing-the-bom-structure-of-an-assembly-part#h.8pgkn6a4kje)

### Costing

Once you've finalized the labeling and hierarchy of all parts in the tree, select a child part from the tree or from the Assembly components section to open it and start adding costing.

![](https://lh5.googleusercontent.com/18cz2lPzPX_VPi48WEenepbLrMMxSuDn16cyQcoOzEe5nI5v_GoH53JwnFla0EJOuvH4Eg-xy-y4wOkMnhhwp47UPdtpNgBTVw-kch54Cl_cs45TNxRNNc-Hg5C3O28IIsqlnhpJS-UFkxyNJ_hzxtk)

*Note*: Whenever you're looking at costing for a child part, there will a bright blue banner at the top of the screen. Scrolling above the blue banner will take you to the costing for the top level of the assembly part.

[Add costing](https://help.paperlessparts.com/s/article/costing-a-part) to the child part. Once you're done, change the part's status to "Complete".

![](https://lh6.googleusercontent.com/vEdrQxIuiu20e_sOjuiNLddrxKiq2ET8OCpT3EVlkrmsKhGv38dyL0U0rwxVhiVGKVO-UC4lLyQScogYjxaHyJCFo1C-GySIgG0WJkRecFXrP3kjrvmOS61gReUBdl448qCVfWcoJHl2zKrO1mg2TaA)

*Tip*: Marking parts as complete will help you keep track of your work in both the navigation bar and the Assembly components section. Complete parts will be indicated by a green check in both places.

![](https://lh4.googleusercontent.com/vfOVTgKZ9XiY3jUlu1wxTUbtBAIBkas_if8KRhJBDSsosm1sEdqkS-CUNkZhAphGPxMV8Um-lhvoY4Qi6cHC9brRnQCkSTQ1cgsAL6m9NrZ6z1sZIRFxpN0xIspbqgCSmdZAddKKM648oeDNMTpgoL8)

Once all child parts are complete, scroll below the Assembly components section and finalize the quote item's pricing the same way you would for a single-component part.
