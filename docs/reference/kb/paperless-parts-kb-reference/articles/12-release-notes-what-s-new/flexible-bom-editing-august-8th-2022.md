---
title: "Flexible BOM editing - August 8th, 2022"
slug: flexible-bom-editing-august-8th-2022
source: https://help.paperlessparts.com/s/article/flexible-bom-editing-august-8th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Flexible BOM editing - August 8th, 2022

> Source: https://help.paperlessparts.com/s/article/flexible-bom-editing-august-8th-2022  
> Topic: Release Notes (What's New)

# Whats new in v24.28.0?

We are excited to release some significant improvements to the BOM editing experience in Paperless Parts. The BOM is the centerpiece to any assembly quote, and we hope to empower our users with these new tools to send more accurate quotes, with fewer mistakes, in less time. Let's talk about the new features:

### Move down a BOM level

Take any component in a tree structure, regardless if it is manually built or derived from CAD, and move it beneath subassemblies within the child BOM.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f1516f6d67192dc61b8d9a/file-QjBwZ4psxX.gif)[See more here](https://help.paperlessparts.com/s/article/editing-the-cad-extracted-bom).

### Move up a BOM level

Take any component in a tree structure, regardless if it is manually built or derived from CAD, and pull it up one BOM level in the tree structure.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f152056d67192dc61b8da2/file-6UGhqXx0WZ.gif)[See more here](https://help.paperlessparts.com/s/article/editing-the-cad-extracted-bom).

### Extract subcomponents out as separate line items

Use the "Move up a BOM level" action for components at the root level to extract them out as separate line items. This is also a great way to undo merging multiple quote items into an assembly.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f153386d67192dc61b8db2/file-c55CSRYiFO.gif)

[See more here](https://help.paperlessparts.com/s/article/quoting-children-of-assemblies-as-separate-parts).

### Editing CAD-extracted quantities

Another situation where the CAD-extracted BOM may be incorrect is when the node quantities are incorrect. The customer may have forgotten to add in a few pieces of hardware or included a duplicate of a geometry as a reference construction or as a mistake. In this situation, you can simply edit the CAD-extracted quantity in the child BOM.

![](https://d33v4339jhl8k0.cloudfront.net/docs/assets/5be4842c04286304a71c0d57/images/62f11bbd61ff5d5f24f99c39/file-KWK1uyGSIE.png)

**Note**: If you edit the node quantity of a subassembly, the system will automatically update all of the flat, BOM, and make quantities of itself and all of its child components.
