---
title: "Managing materials"
slug: managing-materials
source: https://help.paperlessparts.com/s/article/managing-materials
topic: "Setup, Config & Org Settings"
captured: 2026-06-19
---

# Managing materials

> Source: https://help.paperlessparts.com/s/article/managing-materials  
> Topic: Setup, Config & Org Settings

This article will explain how to set up Paperless Parts to create the best material selection experience for your shop and your customers.

#### On this page

- Video summary
- When is material selected for a quote?
- How to customize the global material selector
  - All Materials option
  - Supplier Materials only option
- Process-specific material options
- FAQ

### Video summary

###

### When is material selected for a quote?

There are two places where materials will be selected for quoting. The first is by a Paperless Parts team member in the Build-A-Quote (BAQ) screen when uploading files or changing material for line items:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff32a81551e0c2853f38e4e/file-N1ndlnlk8t.png)The second location is in your Request-For-Quote (RFQ) form by YOUR customers when requesting a quote:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff32b0dfd168b777353144c/file-NGtSwvkEuC.png)

Each process will either use a managed list of materials specified in the individual process or defer to the global material selector. The material options and how they are presented for each process will be the same for your shop when selecting a material on the BAQ page and for your customers on the RFQ form.

NOTE: Both of these material selectors are searchable! Simply start typing the class, family, or name of the material where you see "Select Material" on the BAQ form and "Search" on the RFQ form to get results:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff33b40fd168b77735314c3/file-KslwOYL4vg.png)

### How to customize the global material selector

You can customize your shop's global material selection experience in the Configure tab.

In the **Processes** page of Paperless Parts in the **Materials** tab, there is a gear icon in the top right where you can customize how the material selector looks by default for your shop.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff32bea66df373cab705eb0/file-GIjrhxQNjt.png)Click **Update Material Selector Settings** and following modal will appear:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff32c16551e0c2853f38e58/file-8sNxFRScHD.png)Here, you can update the settings of the material selector and customize its appearance.

#### All Materials option

If the **All Materials option** is selected, all materials (except for those explicitly excluded in the "Excluded Options" settings) will be available for selection in the global material selector. You can exclude individual classes, families, and materials if you do not want them to clutter the interface or do not want them available for customers to choose from when submitting an RFQ. For example, most fabrication and CNC shops can likely exclude the "Additive" and "Wax" material classes. You can then optionally exclude certain families or materials that you do not want to be available.

For example, I have excluded the "Copper" material family and "Inconel 625" material. Here is what the settings would look like:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff32d7d66df373cab705ec4/file-dSV3CHhAEZ.png)

By default, your shop will have the **All Materials** option selected and no excluded classes, families, or materials.

Material families that belong to an excluded material class will also be excluded, e.g. you do not need to explicitly exclude the "Aluminum" material family if you have already excluded the "Metal" material class. The same goes for excluding individual materials. If a material belongs to an excluded material family, the material will also be excluded, e.g. you do not need to exclude "Aluminum 6061-T6" if the "Aluminum" material family is already excluded.

NOTE: Whenever a material is selected either through the RFQ form or in the BAQ page that DOES NOT already have a corresponding supplier material, a placeholder supplier material will be created for the corresponding global material with all fields left blank (e.g. custom name). If you want to update the name or add properties to the material, you can navigate to the global materials page, or update the material in line when quoting the material. When the supplier material is simply a placeholder and not "setup," there will be a yellow warning sign on the BAQ page. Simply click "Edit Material Properties", make any updates (if necessary), and click save to remove the placeholder status.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff35182fd168b7773531590/file-5iXGXa1zxk.png)

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff35480b5efec03af3efb72/file-oG36O5KSKQ.png)

#### Supplier Materials Only option

Alternatively, you can select the option **Supplier Materials Only**. With this option selected, only the global materials you have explicitly created supplier materials for will appear in the material selector. This setting is designed for shops that strictly work with a certain suite of materials for all of their processes and/or want to strictly manage what materials are available in the RFQ form at all times. This option pairs well with the functionality to bulk import your shop's common materials using the **Import Supplier Materials** option found in the gear menu drop down in the top right of the **Materials** tab. (NOTE: We highly encourage you go through our Support channel to bulk import your materials. Re-importing materials at a later date could have some undesirable side effects.) If at any time you then want to offer fewer or more material options, you can add or remove these options one by one in the **Materials** tab. [This](https://help.paperlessparts.com/s/article/adding-a-supplier-material) article explains how to add a supplier material.

When you have the **Supplier Materials Only** option selected, your material selector will take the same "cascading" shape, but now only contain the options you have explicitly created through an import or in the **Materials** tab.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff35c9066df373cab706054/file-t0zREMDV1L.png)

NOTE: You can view both the Paperless Parts global materials database and your own supplier materials list in CSV format by exporting it from the "Materials" tab. Look to the gear icon drop-down menu:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff3376cfd168b77735314a2/file-JOgsoObsuN.png)

### Process-specific material options

We understand that certain processes within your shop might need to be limited to a certain subset of materials. For example, for a forming process, Aluminum 6061-T6 would be an incompatible material since it cannot be reliably bent. Perhaps you want to limit materials for a certain process because you specialize in quick turnaround, and you only stock certain materials. Another example is additive processes, where the machines are only compatible with a concise list of specific materials. Paperless Parts allows you to specify whether an individual process will use the global material selector or its own personalized list of compatible supplier materials.

By default, a process will defer to your global material selector settings:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff35d2c66df373cab70605d/file-XFA2anmuOi.png)

And alternatively to only have a certain list of supplier materials be available for the process:
 ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff35d4ebb5c6f7434e0d852/file-nr5h7YRLyS.png)When only a discrete list of materials are available for the process, you have additional configuration settings. You can set the materials to appear as a list or in the cascader format. The list display will look as follows on the BAQ and RFQ form respectively:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff339d0b5efec03af3efa7b/file-I7O6tQxrdL.png)![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff33a18fd168b77735314b3/file-noj9pKdaDE.png)And now on the cascader display on BAQ and RFQ form respectively:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff33a5a66df373cab705f2d/file-mBvWOFgwe2.png)

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5ff33a74b5efec03af3efa83/file-f7LErR6ahZ.png)We recommend you use the cascader display if you have a very long list of managed materials for a process. The cascading display provides a better selection and search experience.

**FAQs**

**Q. What is the advantage of offering all materials in my RFQ Form?**

A. You allow the customer to communicate exactly what materials they want to use and you do not discourage customers from submitting an RFQ in case the material they want is not present in your list. Many of our most successful CNC shops offer almost all materials. When they find the customer asking for materials that are not optimal, these shops use it as an opportunity to educate their customer, leading to a stronger supplier-customer relationship.

**Q. When should I use a limited list of materials for my process?**

A. You should use a limited list of materials for a process when you only want to allow that list of materials to be quoted for that process. This will usually be the case for additive-type processes. This is also useful for shops that want to limit their RFQ inbound to a subset of materials, particularly for fast turnaround work. While we generally do not recommend limiting material options when it is not absolutely necessary, sometimes it is necessary to minimize no-quotes.

**Q. How do I add multiple colors/heat treats/variants of the same material?**

A. You can quickly add a supplier material for a corresponding global material by following the instructions [here](https://help.paperlessparts.com/s/article/adding-a-supplier-material).
