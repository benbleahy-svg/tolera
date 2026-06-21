---
title: "Replace referenced part with new version - August 25th, 2022"
slug: replace-referenced-part-with-new-version-august-25th-2022
source: https://help.paperlessparts.com/s/article/replace-referenced-part-with-new-version-august-25th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Replace referenced part with new version - August 25th, 2022

> Source: https://help.paperlessparts.com/s/article/replace-referenced-part-with-new-version-august-25th-2022  
> Topic: Release Notes (What's New)

## Whats new in v25.1.0?

We have released improvements that streamline the frustrating experience of running into situations where you cannot perform an action because a part is referenced in multiple quote items. We have released the following:

- Proactive disabling of actions that are restricted when a part is referenced by multiple quote items (with tooltips)
- A new quote item action called "Replace referenced part with new version". This will create a new part to freely manipulate when quoting.

**No longer** will your quoting experience be interrupted by cryptic error messages when you are trying to perform actions in a quote item that attempt to manipulate data such as purchased component reference or the primary file. You will no longer experience the following:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f44e004181f8597e7d15b5/file-pFuma4uzoD.gif)

Now, any actions you cannot perform will be proactively disabled, and they will have tooltips telling you to replace the referenced part with a new version to perform this action:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/630801884cde766bbe13f33e/file-4A2IWNwTYp.png)

Previously the "Deep copy quote item" functionality was the only way to generate a new version of the referenced part that was only referenced by a single quote item, allowing the user to freely manipulate the data on the part. This workflow was click intensive, confusing, and slow.

### Why do I even need to replace the referenced part with a new version?

You need to replace the referenced part with a new version because the action you are trying to perform will manipulate data stored on the part that is being referenced in other quote items. A **part** is where the primary file, geometry, and assembly structure is stored. When you are quoting a part, you are actually working with an object called a **component**. A component is where all of your materials, operations, and other pricing logic lives. This pricing logic *references the underlying data* stored on the part to automatically populate variables like volume, bend count, quantity per assembly, etc. In the quotes page, doing certain actions like switching the primary file, merging line items, making/converting to assemblies, or updating the assembly structure is actually changing data at the part level as well as at the component level. To preserve the data associated with other quote items, we require that you have an underlying referenced part that is only referenced by a single quote item to perform these types of actions. Replacing the referenced part with a new version will essentially sever the connection to other quote items, and allow you to manipulate the part data freely.

Previously, your only option to create an exclusive part to reference was to deep copy the quote item using the "Deep copy quote item" action. This action creates an additional quote item directly beneath the quote item that is being deep copied. In most situations, you would then have to delete the original quote item. To help improve this workflow, we have added a new action to the quote item called "Replace referenced part with new version". This action will simply replace the underlying part data in the quote item you are currently working on with a fresh copy. This will generate an exclusive set of part data to modify without the extra clicks to delete the quote item you are deep copying from:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63080bc290c29a3d732c1e51/file-falhA0Ng10.png)

Additionally, in order to help preserve data integrity between quote items that reference the same part, we have expanded the actions you are not allowed to perform if a part is referenced by multiple quote items. Those actions are:

- Editing custom part attributes
- Manually editing part geometric properties
- Upload component file
- Add manual sub assembly
- Add manual manufactured component
- Add manual purchased component
- Delete component from flat BOM
- Delete node

These are added on top of the existing actions you cannot perform on a part referenced by multiple quote items, and thus require you to replace the referenced part with a new version:

- Switching the primary file
- Changing purchased component reference
- Converting to purchased component
- Converting to manufactured component
- Update node quantity
- Move node up
- Move node down
- Make assembly
- Merge quote items as supporting files
- Merge quote items as components

Refer to [this article](https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq) on deep copy/replacing referenced part for a more in depth description on how the deep copy features work, where and when to use them, and why we built them.
