---
title: "Deep copy / Replace referenced part FAQ"
slug: deep-copy-replace-referenced-part-faq
source: https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq
topic: "Other / Reference"
captured: 2026-06-19
---

# Deep copy / Replace referenced part FAQ

> Source: https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq  
> Topic: Other / Reference

**What does it mean when the system says I have to "replace the referenced part"?**

You may encounter a disabled button that is not usually disabled, accompanied by a tooltip that looks something like:

*"You cannot ______ because the part is referenced by multiple quote items; to do so, replace the referenced part with a new version."*

Below is an example of an action, switching the primary file, where you may encounter this situation:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/630804e190c29a3d732c1e3e/file-qOdaW0XAlF.png)

This means that the part you are working on is currently being referenced by multiple quote items, and the action you are trying to perform is blocked because it will manipulate data that is being referenced in other quote items. This **includes** if the part is being quoted multiple times within the same quote.

To create an exclusive set of data for just the quote item you are currently working on to reference, you must replace the referenced part with a new version. Alternatively, you can perform a "Deep copy quote item" action that will generate a new quote item with an exclusive copy of the part data, where you can make your edits there. Both of these actions *will create a new part in your part library*. To replace the referenced part with a new version or deep copy a quote item, you can use one of two actions by clicking the 3 dots on the left sidebar: "Deep copy quote item" or "Replace referenced part with new version".

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63080bc290c29a3d732c1e51/file-falhA0Ng10.png)

### What is the difference between "Deep copy quote item" and "Replace referenced part with new version"?

"Deep copy quote item" will create a new entry in your part library and create a new quote item directly beneath the quote item you have copied:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/630806f24cde766bbe13f352/file-9oBtRDDWPQ.gif)

You should use "Deep copy quote item" when you are using a "template part" workflow, where you have similar parts in the same quote package, and you want to use the structure and data from a part you just created as a starting point for another line item.

"Replace referenced part with new version" will create a new entry in your part library, but it will not create a new quote item:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/630806e8037bc877147b3313/file-z7Au2voJjs.gif)

You should use "Replace referenced part with new version" when you want to manipulate data on the part within the quote item you are currently working on. This will be most commonly used after you have copied a quote, made a revision of a quote, or added a part to a quote from the part library.

### Why do I even need to replace the referenced part with a new version?

You need to replace the referenced part with a new version because the action you are trying to perform will manipulate data stored on the part that is being referenced in other quote items. A part is where the primary file, geometry, and assembly structure is stored. When you are quoting a part, you are actually working with an object called a component. A component is where all of your materials, operations, and other pricing logic lives. This pricing logic *references the underlying data* stored on the part to automatically populate variables like volume, bend count, quantity per assembly, etc. In the quotes page, doing certain actions like switching the primary file, merging line items, making/converting to assemblies, or updating the assembly structure is actually changing data at the part level as well as at the component level. To preserve the data associated with other quote items, we require that you have an underlying referenced part that is only referenced by a single quote item to perform these types of actions. Replacing the referenced part with a new version will essentially sever the connection to other quote items, and allow you to manipulate the part data freely.

### What actions are disabled if a part is referenced by multiple quote items?

- Editing part number, revision, and description
- Editing custom part attributes
- Manually editing part geometric properties
- Upload component file
- Add manual sub assembly
- Add manual manufactured component
- Add manual purchased component
- Delete component from flat BOM
- Delete node
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

### When will these actions be disabled?

You can run into a situation where you have an underlying part that is referenced by multiple times by doing any of the following actions:

- Copying quotes
- Making quote revisions
- Adding parts to a quote from the part library
- Duplicating quote items in a quote

### What's the difference between Deep Copy vs. Duplicate Quote Item?

Duplicate Quote Item: This action creates another instance of the quote item. There will *not copy the underlying part data*, and thus will not create a new entry in your part library.

Deep Copy: This action is essentially re-uploading and copying the part. There will be a new part in your part library after this action is completed. The only quote item associated with this part file will be the one you just created with the action.

### I created a copy/revision of my quote, are the items deep copied or duplicated?

Creating a copy or revision of your quote will ***duplicate***the quote items, **not**deep copy. The part will now exist in both the original and new quote and may require you to manually deep copy the item if attempting to perform one of the actions listed above.

### How do I view the other quote(s) a part file exists on?

Navigate to the part viewer and then click on the Quotes/Orders tab ($ icon) in the left navigation. This will list all quotes and orders that the file is tied to, with the quote/order status next to it.

*Tip -*Are you getting chat notifications and getting confused about which quote it is referring to?

- Hovering your mouse over the message will give you a link to the quote, or the part viewer depending on where the message was sent from.

### What data lives at the quote, quote item, component, part, and file levels?

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6306c24566967f4ba394aeca/file-QgNO18Mvc0.png)

### What data gets copied when copying a quote/making a quote revision?

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6306c28bb67994108536ab55/file-Ww3luJItkm.png)

### What data gets copied when using "Duplicate quote item"?

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6306c2a766967f4ba394aecc/file-oKQ5PzMrl3.png)

### What data gets copied when using "Deep copy quote item"?

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63080ff0c713d51da3ed8c52/file-XVfwgtHPQ6.png)

### What data gets copied when using "Replace referenced part with new version"?

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63080f9990c29a3d732c1e5c/file-xkiBEa24ec.png)
