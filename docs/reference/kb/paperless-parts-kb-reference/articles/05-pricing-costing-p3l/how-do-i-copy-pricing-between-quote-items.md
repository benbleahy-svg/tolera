---
title: "How do I copy pricing between quote items?"
slug: how-do-i-copy-pricing-between-quote-items
source: https://help.paperlessparts.com/s/article/how-do-i-copy-pricing-between-quote-items
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# How do I copy pricing between quote items?

> Source: https://help.paperlessparts.com/s/article/how-do-i-copy-pricing-between-quote-items  
> Topic: Pricing, Costing & P3L

Learn how to use the **Copy pricing** action to push costing and pricing from one quote item to another, including material selection, operations, finishes, and overrides.

This action can be especially helpful when quoting two similar parts (such as left-hand and right-hand components of a part), driving consistency while also helping you turn around a quote quickly.

### On this page

- [How do I copy pricing between quote items?](#h.oa6f2zfla46b)
- [FAQ](#h.o4ngul2jp7m3)
  - [What does the Copy pricing action include?](#h.qkhhrswpoe8r)
  - [What happens if I copy pricing to a quote item that already has costing?](#h.etxc791htw8g)
  - [How does Copy pricing work in assemblies?](#h.5mwubi1kxg1a)

---

# How do I copy pricing between quote items?

1. Start from the quote item you will be copying pricing *from*.
2. Click the three dots next to the quote item and select **Copy pricing**.
3. Select the recipient part (or parts).
  1. Use toggles to specify what to bring over from the initial quote item.
4. Click **Copy pricing** to confirm.

## Written walkthrough/example

Let's say you receive an RFQ for part #5-X-9 rev C, and you previously quoted revision B of that same part.

- Both revisions are made out of Aluminum 6061-T6 and are anodized.
- Revision B included an add-on for tooling, but you don't need to charge for that on revision C.
- The buyer wants a quote for quantities 10, 25, and 100.

To turn around the quote as quickly as possible, let's copy pricing from 5-X-9 B (quote #4281) to 5-X-9 C (quote #4282).

Navigate to the quote for 5-X-9 B (the part that you've already quoted).

Click the three dots next to the quote item and select **Copy pricing**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6480cafe7f8c2575e3544805/file-839EeZc6Ud.png)

Select which part you want to copy pricing to (the recipient part).

If the part is in a different quote (as it is in this example), select **Choose different quote** to browse your draft quotes and choose a recipient quote item.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/647f2e30aef24e1deb40de63/file-OHsVQeqy3y.png)

Recall that we want to copy over materials, routing, and quantities, but not add-ons. In this case, that means we should select material, operations, pricing items, and quantities, and deselect add-ons.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/647f2ee495b6b2126f5265b9/file-zU4RAa7o9V.png)

Click **Copy pricing** to confirm.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/647f2f0faef24e1deb40de65/file-AiTdMbsOyH.png)
A green window will appear confirming that you successfully copied pricing. Click the link to view the recipient part and confirm that pricing came over correctly.
![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6480cb51969cec658daaf3c9/file-ykKIWrrhBb.png)

Part # 5-X-9 C now has the same exact price as part # 5-X-9 B. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6480cb757f8c2575e3544806/file-1GrQhT5LJS.png)

# FAQ

## What does the Copy pricing action include?

You can select what you bring over with the **Copy pricing**action, including:

- Material
  - Copy the process name and material assigned to the source part. (Updating the process name in this case will not impact operations or pricing items.)
- Operations
  - Copy the process name, costing items, and costing item overrides.
- Add-Ons
  - Copy the add-ons and add-on overrides.
- Pricing items
  - Copy the markups and margins and pricing item overrides.
- Discounts
  - Copy the discounts and discount overrides.
- Quantities
  - Copy the quantities, yield, and lead time, including any overrides made to yield or lead time.

**Copy pricing** will *not*bring over:

- Part files
- Geometric attributes
- Part number/revision
- Part description
- Manufacturing notes
- Custom attributes
- Hardware
- Workflow status

## What happens if I copy pricing to a quote item that already has costing?

The existing costing on the recipient part will be replaced by the pricing you copy over.

## How does Copy pricing work in assemblies?

Copying pricing between children of assembly parts is functionally similar to copying pricing between quote items.

Select the checkbox of the child part you are copying pricing *from* in the **Assembly components**section.

Click **Actions** and select **Copy pricing**.

![](https://lh6.googleusercontent.com/UiHE1myLrWAFyqd07u9gi3U-UTZGrhdMaPK4sk-OrFUPq1qRFBaNenQV-DUSiUy6M51PoVwBT7lxB_TzH9mROMmEw053HOM0YC-ousjxJBIxxu05X4FVKEyURSJFIFwQndKKhrnyV4Bvzea6K0wWUzg)

*Note*: Currently, copy pricing only works between single-component parts. You cannot copy pricing to or from an assembly/subassembly part and its children in one action.
