---
title: "Multi-component sheet metal nesting"
slug: multi-component-sheet-metal-nesting
source: https://help.paperlessparts.com/s/article/multi-component-sheet-metal-nesting
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Multi-component sheet metal nesting

> Source: https://help.paperlessparts.com/s/article/multi-component-sheet-metal-nesting  
> Topic: Part Analysis & Interrogation

Optimize the cost of material and labor for multiple sheet metal parts by predicting shared cutting patterns.

#### On this page:

- Quick start guide
- Nesting requirements
- Video tutorial
- Written walkthrough
- FAQ
  - Nest eligibility
  - Compatibility
  - Nestable operations

Looking to implement nesting in your account? Reach out to [our Support team](#) to configure your nestable operations and start nesting!

---

# Quick start guide

*For a more detailed walkthrough and tutorial video, see the*[Walkthrough section](#video)*below.*

1. Quote as normal, assigning a process, material, and any finishes, as well as setting customer-requested quantities.
  1. Ensure that your quote meets all nesting requirements before proceeding and that all operations you expect to be optimized have the Nestable badge displayed.
2. Open the nesting module.
  1. This can be done within a quote item, either from the Sheet Metal Interrogation panel, within a nest-compatible operation, or from the top level of the quote in the Actions menu.
3. Select parts you'd like to nest together, optionally using Select All Compatible for efficiency.
4. Fill out the Nest Preparation Form, and hit Generate.
5. Wait for the nests to finish generating. Click the resulting nest in the sidebar or the Nested? column of the table to view results.
6. Before finalizing your quote, confirm that costs have been optimized by checking the badges on nest-compatible operations.

---

# Nesting requirements

The following requirements must be satisfied in order for a part to be eligible for nesting.

1. Each component either has a 2D DXF file or a 3D model that has been unfolded.
  1. To unfold a 3D model and get a flat in Paperless, assign an operation that calls a sheet metal interrogation.
    1. Any operation performing a geometry-based calculation (such as laser cut time) calls an interrogation.
2. Each component has an assigned material, thickness, and nest-compatible material operation.
  1. Thickness will come in manually for 3D models but needs to be entered for 2D files on upload.
3. Each component's make quantity is accurate.
  1. This value cannot be adjusted after nesting.

Any part that you have quoted as normal will likely meet these requirements, but you can confirm by checking the badge next to a part's flat pattern.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63653e2d9e210557927acc55/file-NAgmJVFOOy.png)

---

# Video walkthrough

# Written walkthrough

Begin by quoting as normal. While working through your quote, be sure to confirm that each part you would like to nest meets the [nesting requirements](#requirements) detailed above and has the nest-eligible badge.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372d139bedde91b3d8c91a3/file-KYBZPnLdly.png)

Open the nesting module, either directly from the **Sheet Metal Interrogation** banner or from the **Actions** menu in the main quote area.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372d1ca6c146d4e429d06a2/file-xB0aAuHMxu.png)![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372d1e9bedde91b3d8c91a5/file-EO7UsM4Hha.png)

Here, the nesting process varies slightly depending on if the components you'd like to nest are from the [same quote item](#same-qi) (such as assembly components) or [multiple quote items](#across-qi). The process will be the same for both again starting at the [All components](#resume) section.

## Nesting parts from the same quote item

Select the parts that you'd like to nest, either by clicking each part's checkbox or by using the **Select all compatible** option. Parts from the same quote item are considered [compatible](#compatibility) with each other if they have the same material, thickness, make quantities, and [nest-compatible operation](#cost).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372d3073fc88c6e0f0069f5/file-d6BqkdajHt.png)

Once you've finalized your selections, click **Prepare Nest** to open the nest preparation form.

Fill in any relevant details about the properties of the stock you will be using for each quantity, desired nesting behavior, and pricing.

For users without ERP systems, simply enter a sheet cost for each quantity. If you have an ERP integration and want to pull pricing for a specific sheet, enter an ERP code to search your material table. (The values in this table will be pulled from your ERP system.)

Be aware that manually typing a value into the **Sheet cost** field will override any information coming in from your ERP, even if you enter an ERP code.

*Note: Be sure to review operations after nesting to confirm that the cost was captured correctly from your material table.*

If your parts have a grain direction requirement, you can assign a lengthwise or widthwise grain direction for the sheet in the **Stock properties** section.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372d6616c146d4e429d06a7/file-ji709LTJv4.png)

Then set the orientation requirement for each part in **Component settings** (either along length or width).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372d6ab3fc88c6e0f0069f8/file-i40Saag7Sx.png)

Click **Generate nest**. This will create a separate nest for each make quantity.

*Note:*Use the "Swap Units" button toenter nesting information in a different system of measurement (ex. millimeters instead of inches).

![](/servlet/rtaImage?eid=ka0Ns0000000iYv&feoid=00N5G00000WB8Hk&refid=0EMNs00000GKLwj)

## Nesting across quote items

Select the parts that you'd like to nest, either by clicking each part's checkbox or by using the **Select all compatible** option. Parts across quote items are considered [compatible](#compatibility) with each other if they have the same material, thickness, and [nest-compatible operation](#cost). They should also both have a *single* make quantity.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372dacf3fc88c6e0f0069fb/file-j08TYQ8bDt.png)Once you've finalized your selections, click **Prepare nest** to open the nest preparation form. Here, fill in any relevant fields about the properties of the stock you will be using, desired nesting behavior, and pricing.

For users without an ERP integration, simply enter a cost in the **Sheet cost**field. If you have an ERP integration and want to pull pricing for a specific sheet, enter an ERP code to search your material table. (The values in this table will be pulled from your ERP system.)

Be aware that typing in a sheet cost will override any information coming in from your ERP, even if you enter an ERP code.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372db546c146d4e429d06aa/file-zjxktCbrpK.png)

*Note: be sure to check operations after nesting to confirm that the cost was captured correctly from your material table.*

If your parts have a grain direction requirement, you can assign a lengthwise or widthwise grain direction for the sheet in the **Stock properties** section.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372db8a3fc88c6e0f0069fe/file-I9WYscfiMt.png)

Then set the orientation requirement for each part in **Component settings** (either along length or width).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372dbccaad33a6d7c946b6e/file-gzpiHbH4J4.png)

*Note: Because the nest-optimized costs will only be valid if your customer orders all of the parts you've nested together, online checkout will be disabled for any quote with a nest across multiple quote items. You and your team will receive multiple warnings before finalizing a quote that falls into this category, but be sure to communicate to your customers that they need to order all nested parts to receive optimized pricing.*

Click **Generate nest**.

*Note: Extremely complex nests (those with hundreds of components) may take up to five minutes to load but will continue to generate even if you leave the module, so don't be afraid to do something else in the platform (or grab a cup of coffee!) while you wait.*

#### All components

You can view completed nests either by clicking on the nest in the sidebar or in the **Nested?** column for each component. These results include nest-level statistics as well as statistics for the specific sheet type.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372dcdfbedde91b3d8c91a9/file-sphz7W25zg.png)

For part-specific information, including cost distribution, select **Components in Nest**.

To delete a nest, click **Actions** in the top right corner and select **Delete nest**.

*![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/645946e44307f26bfc141469/file-0Yxv91fTTW.png)*

*Note: Deleting one nest that includes parts with multiple make quantities will delete the nests for the other make quantities as well.*

Operations optimized by a nest will now be marked as **Nested**, and core variables will be updated accordingly.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372dd6bbedde91b3d8c91ab/file-4QZjtx1WU5.png)

## Regenerating existing nests

To make changes to an existing nest, open it in the nesting modal and click **Actions**in the top right corner. Select **Regenerate nest**to reopen the nest preparation form.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6459489f4307f26bfc14146c/file-rKKo6cTYdr.png)Edit inputs as needed and click **Regenerate nest**to confirm. The old nest will be deleted and a new one will be created with the updated inputs.

*Note:*If the nest you are regenerating is part of a set (i.e. you nested a part with multiple make quantities), the changes you make to the nest preparation form will persist across all associated nests. In this example, regenerating nest #1 will also regenerate nests #2 and #3 with the new inputs. *![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64594e984307f26bfc141477/file-6Zlyi9pJOJ.png)*

## Downloading nests

To download an existing nest as a PDF, open it in the nesting modal and click **Actions** in the top right corner. Select **Download nest as PDF.**

*Note*: Download permissions are required to be able to download a nest locally. Downloading a nest PDF with CUI parts in it will trigger a CUI downloaded event in our IT module's "CUI audit" CSV export.

---

# FAQ

## What makes a part nest eligible?

A component is nest eligible if it meets all of the [requirements](#requirements) outlined above. Nest eligible components will have a badge in their **Sheet Metal Interrogation Results** letting you know that the part is eligible for sheet metal nesting.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63653e2d9e210557927acc55/file-NAgmJVFOOy.png)

## Can I generate a nest for multiple make quantities?

Only if the components you would like to nest together are in the same quote item (e.g. assembly components) and are compatible with each other. The workflow will be the same until you reach the Nest Preparation Form, at which point you will also need to enter quantity-break-specific stock options for each make quantity. A nest will be generated for each make quantity.

## What makes parts nest-compatible with each other?

It depends - are you nesting [multiple parts within one quote item](#same-qi), such as components of an assembly, or [parts across multiple quote items](#across-qi)?

Parts within the same quote item are compatible if they have the same thickness, material, and nestable operation. Nesting two components with multiple make quantities will create a nest for each quantity.

Parts across multiple quote items are considered compatible with each other if they have the same material, thickness, and nestable operation. They also need to have one make quantity each. Even if two parts across quote items have the same thickness and material but they have multiple make quantities, they will not be considered nest compatible. This is because we cannot currently enforce that customers purchase the correct, optimized set of parts from the digital quote.

## What is a nestable operation? How will sheet metal nesting optimize the cost of my quote?

Any operation that can be optimized by a sheet metal nest is considered sheet metal nest compatible and will have a badge announcing that the operation is **Nestable.**

**![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372ddd9aad33a6d7c946b6f/file-GBYyCRGo2f.png)**

If an operation's cost has been optimized by a nest, the badge will turn green and say **Nested**.
![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372ddfafd962f4d057baf51/file-2BJV4I225n.png)

To tell if an operation can be optimized by sheet metal or linear metal nesting, check the symbol on the **Nestable**badge.

| **Linear nest compatible badge**![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63a387619cef114e6cd202b1/file-cSxihh1aT8.png) | **Sheet metal nest compatible badge**   ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63a3877e19e7612677172231/file-xx3Kg7FaTv.png) |
| --- | --- |

Keep in mind that any variables that you override before nesting will **not**be affected by a nest. Ensure that all nestable operations do not have any overrides before nesting.

The specifics of how a nest will optimize the cost of an operation will be determined by your TIS. Be sure to communicate with your Paperless team about how you expect nesting to impact your quote.

## Why can't I change a part's make quantity or delete a nestable operation from the router?

Certain actions, such as changing a part's make quantity or deleting a nestable operation, will be locked in the presence of a nest. To adjust one of these values, you'll first need to delete the nest for that part or [Replace referenced part with new version](https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6372e051bedde91b3d8c91b0/file-88PjEUV5QP.png)

## How can I implement nesting in my account today?

Reach out to [our Support team](#) to get nestable operations configured in your account.
