---
title: "Swap primary and supporting files"
slug: swap-primary-and-supporting-files
source: https://help.paperlessparts.com/s/article/swap-primary-and-supporting-files
topic: "Setup, Config & Org Settings"
captured: 2026-06-19
---

# Swap primary and supporting files

> Source: https://help.paperlessparts.com/s/article/swap-primary-and-supporting-files  
> Topic: Setup, Config & Org Settings

#### On this page

- Primary vs. supporting files
- How to swap the primary file
- Restrictions and special cases when swapping primary files
  - Primary files for parts that exist in multiple quotes
  - Primary files for line items that do not have a primary file
  - Primary files for assembly parts and child parts of assemblies

# Primary vs. Supporting Files

Each part in your library can have associated part files, including one primary file and multiple supporting files.

The **primary file** acts as the source of truth for a part and dictates information like:

- Geometric attributes
- Features
- BOM structure

... making it critical that you assign the file with *the most geometric information* as a part's primary file (like a CAD file).

**Supporting files**don't impact part definition, but they're a great way to capture additional part information - like technical drawings with additional details or quotes from vendors. They'll stay with the part so that you can reference them if you ever need to requote it.

Paperless Parts will only rely on the primary file for information about a part, so if you upload a print to create a quote item and then attach a solid model as a supporting file, the part's geometry will not autofill with information from the CAD file. In order to access all of the automation that Paperless Parts can provide with CAD files, you'll need to swap the primary file to the model.

Line items without a primary file are called “blank line items” (formerly called “manual parts”).

*Note*: Uploading two files with the same file name (like a CAD file and detail drawing) will create one quote item with the CAD file auto-assigned as the primary file and the other as a supporting file.

# How to Swap the Primary File

To swap a part's primary file, open the line item from the Build-a-Quote page and navigate to the Part Files section. Click the double arrows next to the supporting file that you want to swap as the primary file.

![Screenshot 2024-02-02 at 8.30.15 PM.png](/servlet/rtaImage?eid=ka0Ns0000001GPJ&feoid=00N5G00000WB8Hk&refid=0EMNs000002rAjF)

If a part does not have a primary file, there is no existing primary to swap with. Click the single arrow next to the supporting file that you want to add as the primary file:
![swap primary manual line item.png](/servlet/rtaImage?eid=ka0Ns0000001GPJ&feoid=00N5G00000WB8Hk&refid=0EMNs000002rAsv)

When dragging and dropping files onto a part without a primary file, either from quote files or your computer, you can immediately assign one of the files as the primary file:

![make primary and supporting files.gif](/servlet/rtaImage?eid=ka0Ns0000001GPJ&feoid=00N5G00000WB8Hk&refid=0EMNs000002rAzN)

When uploading multiple files in this workflow, the file with the most geometric information (like a CAD file or a DXF) will be auto-assigned as the primary file and the others as supporting files.

# Restrictions and Special Cases When Swapping Primary Files

Because a part's primary file has such a high impact on its definition, there are a few cases to consider where you can or cannot swap the primary file:

- Primary files for parts that exist in multiple quotes
- Primary files for line items that do not have a primary file
- Primary files for assembly parts and child parts of assemblies

## Part Exists in Multiple Line Items Error

Sometimes, when you go to swap the primary file, you'll receive an error warning saying that the part exists in multiple line items. To move forward with switching the primary file, use the [replace referenced part action](https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq). This will create a new instance of the part in your library that you can alter without impacting any other line items.

More information on this action can be found here: [Deep Copy FAQ](https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq)

## Line Items Without a Primary File

“Blank” line items – line items without a primary file – have some additional capabilities because they do not yet have a primary file. Blank line items can be created one-by-one or [in bulk](https://help.paperlessparts.com/s/article/setting-up-quote-items#bulk) . Once they are created, **any** file can be added as the primary file **until** a process is selected or child components are manually added. This means a CAD model with multiple bodies (an assembly) can be added as the primary file and the BOM will be built out. Make sure the line item does not have a process assigned and avoid manually building out your BOM until you have added your primary file to the root part.

## Swapping Primary Files in Assemblies

Swapping primary files in assemblies can be messy. In general, you should avoid attempting to swap files with files that contain different BOM structures (for example, a CAD file with multiple bodies and a print).

You are not able to swap CAD models with different BOM structures. If you attempt to make a CAD file with multiple bodies (an assembly file) the primary file for a CAD file with a single body, you will see this error message:

This applies to line items as well as child components in an assembly.

For assemblies broken out from a single CAD model, the entire part’s tree is generated from that one file, so you will not be able to change that primary file or the primary file of any child component. If you attempt to, you will see this error message:
![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64791916a563b4000567ccad/file-F0Jgw4KHSJ.png)

In child components of an assembly that has been manually built out (either by uploading files, adding manual components, or merging existing line items as components – read more about our BOM tools [here](https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-pdf)), you will be able to freely switch the primary file except when the files have different BOM structures.

*Tip*: This capability allows you to utilize PDF vectorization when building assemblies from prints. Extract the pages that contain flat patterns from the top level print in the viewer or upload the additional PDF files that may be provided as manual manufactured components. Vectorize these prints and then switch the primary file to the DXF file that is created. The operations on the manufactured components will now reference the vectorized file to drive the geometric inputs of the pricing formulas, like cut length and pierce count. You can see a walk through of this [in this video](https://paperlessparts.wistia.com/medias/dbkryphm6x).

More information about the update to enable assembly component file switching and some other really cool enhancements can be found here: [Flexible Primary File Assignment Update](https://help.paperlessparts.com/s/article/flexible-primary-file-assignment-june-13th-2022)

###
