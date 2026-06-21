---
title: "Quoting children of assemblies as separate parts"
slug: quoting-children-of-assemblies-as-separate-parts
source: https://help.paperlessparts.com/s/article/quoting-children-of-assemblies-as-separate-parts
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Quoting children of assemblies as separate parts

> Source: https://help.paperlessparts.com/s/article/quoting-children-of-assemblies-as-separate-parts  
> Topic: Assemblies & BOM

Has a customer ever asked you to quote you for an entire assembly as well as individual subassemblies underneath the parent level? This article will show you how to do this using the move up in BOM feature.

Let's take an example of the PP-13701224-21.step below. The customer requests a quote for the top level as well as the two major subassemblies within the model, ASM-654 and ASM-224.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f1261f80fd5a31e7ad0136/file-IN1yEkvuQ4.png)

The video below will walk through how to quote the top level as well as the subcomponents within them as separate line items:

To recap the steps you just saw:

1. Upload the CAD model
2. Quote the top level assembly as you normally would
3. Extract each subassembly you want to quote individually from the top level BOM, leaving behind a copy of it in the current top level assembly
4. Finish quoting the subassemblies as their own line items
5. View the digital quote, seeing the subassemblies as separate line items
6. View the line items in the part viewer

## FAQ

#### Where else is this feature useful?

Extracting subcomponents out as their own line item is a very useful "undo" tool after making mistakes when merging multiple line items together as components into an assembly. You may want to build out a manual assembly as a separate line item, and then merge it into the top level of an existing quote item. If you perform this merge at the wrong time or make a mistake, you simply can extract the subassembly out to a separate line item, make your edits, and then merge it back in after.

#### Are the extracted subcomponents linked back to the components in the original assembly?

No. When components are extracted from the assembly, they create entirely new part and component objects. The pricing is not shared between them. They are, however, referencing the same underlying file geometry.

#### Can I download the subassembly or subcomponent files after I extract them to their own line items?

No. Downloading the file from the extracted line item will download the original uploaded file.

#### If I merge the extracted line items back into the original, what will happen?

The line items will be treated as if they were any other line item getting merged in. They will not be intelligently "re-inserted" back into the tree structure where they were found before extraction.
