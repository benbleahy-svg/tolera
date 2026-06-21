---
title: "Flexible primary file assignment - June 13th, 2022"
slug: flexible-primary-file-assignment-june-13th-2022
source: https://help.paperlessparts.com/s/article/flexible-primary-file-assignment-june-13th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Flexible primary file assignment - June 13th, 2022

> Source: https://help.paperlessparts.com/s/article/flexible-primary-file-assignment-june-13th-2022  
> Topic: Release Notes (What's New)

## What's new in v24.11.0

We have removed many of the restrictions around switching primary files with assemblies and streamlined the workflow of building manual assemblies from PDFs. We built these features to make it easier to work with manually constructed assemblies from PDFs. Here is a video summarizing all of the changes:

### PDF files as the primary file of manual assemblies

You can now have the primary file of a manual assembly be a PDF file (or any other type of non-geometric file). Previously, only a manual file could be the primary file of a manual assembly.

**Note**: The "primary file" of a part is what drives the appearance of the thumbnail and the geometric inputs to operations. If the primary file is a CAD file, we will be able to provide high level geometric information like volume, area, and dimensions and interrogation info like cut length, number of bends, and hole counts.

![](https://lh5.googleusercontent.com/fwj_QNVPqfTkBOcuMrWM0OMqWH7T1ZNMiT2ZKoW2FMCdaVxAypWIUMARNcdV-1IVe7tzO693IYgBktCthDyXrKzUFxZjiCFTJv79XoHqfxXXgtTE7IbT1cX8X3gSk7nBc7AnnvlxSJX9hhMspA)

### Improved workflow for "Make Assembly" with PDFs

Previously when uploading a PDF file as its own line item, and then converting that line item to an assembly using the "Make Assembly" action, the user would be forced to demote the PDF to a supporting file or push the PDF file down into a manufactured component. A manual file would then be created to occupy the primary file field on the new top level assembly. Now the "Make Assembly" action will instead simply convert the top level component to an assembly, and the PDF file will remain as the primary file on that top level assembly. This behavior is exactly the same behavior when using the "Make Assembly" action with a manual line item.

![](https://lh3.googleusercontent.com/J7Lhs6GLX7VlWGIrjtaVqt1hR-glv9vOPkiUasFOsgdaDl18nWa_U_r__4ciIyOtCjTGQ--xmr6QjhmKheq_GAPI4q5Cu29qKdEZtw4SzDFYfZjAOYwoCl2BB8LT_CQNJt1JcJm1QmEpAZUPjQ)

**Note**: The behavior of the "Make Assembly" action with a CAD primary file will not change.

### Ability to switch the primary file w/ assembly components

For any manually created components in an assembly structure, either added manually, uploaded manually, or merged in from other line items, you will be able to freely switch the primary file with the following restrictions:

1. You cannot switch the primary file for a component that was automatically generated from a CAD assembly breakout
2. An assembly CAD file (multiple bodies) cannot be made the primary file of a manufactured component
3. A non-assembly CAD file (single body) cannot be the primary file of an assembled component

Previously, you could not switch the primary file for any component in the assembly structure.

**Pro tip**: This capability now allows you to utilize PDF vectorization when building assemblies from prints. Extract the pages that contain flat patterns from the top level print in the viewer or upload the additional PDF files that may be provided as manual manufactured components. Vectorize these prints and then switch the primary file to the DXF file that is created. The operations on the manufactured components will now reference the vectorized file to drive the geometric inputs of the pricing formulas, like cut length and pierce count. You can see a walk through of this [in this video](https://paperlessparts.wistia.com/medias/dbkryphm6x).

### Rapid part deep copy

The "Deep Copy Quote Item" action is now ~20x faster. This deep copy action for large assemblies routinely took longer than 10 seconds…now this action should take no longer than half a second. It will be almost instant for smaller assemblies and parts.
