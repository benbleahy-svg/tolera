---
title: "Quoting an assembly part from a PDF"
slug: quoting-an-assembly-part-from-a-pdf
source: https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-pdf
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Quoting an assembly part from a PDF

> Source: https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-pdf  
> Topic: Assemblies & BOM

Because Paperless Parts can extract a BOM hierarchy from a CAD file, quoting an assembly part off of a PDF rather than a model requires a few additional setup steps. In this document, we'll walk through the fastest way to quote an assembly part from a PDF - both when your buyer gave you individual detail drawings for each child part and when they didn't.

#### On this page

- Quoting an assembly part with all product definition in one PDF
- Quoting an assembly part with detail drawings for each child part

---

# Quoting an assembly part with all product definition in one PDF

When an assembly is fully defined on one PDF file, you'll need to build the BOM structure that best represents your shop's desired method of manufacture and assembly steps *before* you cost and price the part.

Start by [uploading the PDF](https://help.paperlessparts.com/s/article/setting-up-quote-items#h.p0jyhh3420cf) to a quote to create a new quote item. Once it loads, click the three dots next to the quote item and select **Make assembly**to turn it into an [assembly part](https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit#h.1m6ps23tz0rr).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64247be81274e915f2f925bb/file-MphFx0INM6.png)

Navigate to the **Components**section of the quote item to start building the BOM structure.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642487d31274e915f2f925d1/file-X1JprbV621.gif)

To add a child part to the assembly:

- Click **Add components to top level**and select the type of child part you would like to add.

  - [To add a manufactured component](#mfg) (a part that you will make out of a raw material workpiece in your shop), select **Add Manual Manufactured Component**.
  - [To add a subassembly](#sub), select **Add Manual Sub-Assembly**.
  - [To add hardware](#pc), select **Add Purchased Component.**

## Adding a manufactured component

Once you click **Add manual manufactured component**, you'll need to assign a part number to the child part as well as a node quantity (the number of child components at that level of the assembly).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64248cc57bf4bb61c01166ae/file-QxYrVfU1zG.png)

Assign a [process](https://help.paperlessparts.com/s/article/processes), material, and quantity and select **Confirm**to add the part to the assembly. This will add a cube icon to the BOM tree in the navigation bar.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6427337a1274e915f2f928a6/file-nVxHOnkC0c.png)

## Adding a subassembly

Adding a subassembly to your assembly part will create a new level in the BOM hierarchy. After clicking **Add manual sub-assembly**, add a part number and node quantity to the child assembly part. Be sure to select a process that is [compatible with assembly parts](https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit#h.nys9v6p1vafn).

Select **Confirm**to add the subassembly. This will add a grid icon to the BOM tree in the navigation bar.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642734ad7bf4bb61c011698c/file-xYOwzyuDED.png)

To add a child part to a subassembly, select the subassembly from the **Components**section and scroll down to the **Sub-assembly components**section. Click **Add components to sub-assembly**and select the type of part you would like to add, assigning a process and node quantity (number of parts *per subassembly*).

Any child parts you add to this subassembly will appear below the subassembly in the tree in the navigation bar.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642735981274e915f2f928ad/file-giTD6Hw6Sv.png)

## Adding purchased components

Select **Add purchased component**to browse your purchased component library. Either select an existing entry and enter a node quantity or (if the part does not already exist in your library) click **Create new component.**

Once you've finalized your selection, click **Add component**to add it to the BOM structure.

**![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642736e291efbc3c62649fff/file-c9qW2K0kdq.png)**

Once you've completed the assembly BOM structure, you can [add costing to each child part](https://help.paperlessparts.com/s/article/costing-a-part) and [price the top-level assembly](https://help.paperlessparts.com/s/article/pricing-a-part) before sending your quote.

*Note*: Check out our article on [quoting from PDFs](https://help.paperlessparts.com/s/article/quoting-from-pdfs-tips-and-tricks) for tips on how to quickly arrive at a price when working off of a print.

# Quoting an assembly part with detail drawings for each child part

Sometimes, buyers will send you an RFQ whose data package contains an assembly-level drawing with assembly-specific information (like welding instructions, coating specifications, Parts list, torques, etc) along with several individual component drawings that contain item-level product definition. In this scenario, you can drag and drop files into the Components table to create components.

First, upload all of the files for child parts into the Quote files section of the quote.

If you have a print for the top level of the assembly, drag it into the left nav bar to create the line item. Convert it to an assembly and open the line item. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64247be81274e915f2f925bb/file-MphFx0INM6.png)Open the Quote files drawer on the right side of the page and drag and drop files onto the Assembly components table to create new components.

![drag to component.gif](/servlet/rtaImage?eid=ka0Ns0000001Eyb&feoid=00N5G00000WB8Hk&refid=0EMNs000002qpEz)

From there, use the following tools to edit the BOM as needed:

- Change the quantity of child parts
- Move child parts up/down a BOM level
- Add purchased components

Once you're satisfied with the BOM structure of your assembly part, [add costing to each child part](https://help.paperlessparts.com/s/article/costing-a-part) and [price the top-level assembly](https://help.paperlessparts.com/s/article/pricing-a-part) before sending your quote.
