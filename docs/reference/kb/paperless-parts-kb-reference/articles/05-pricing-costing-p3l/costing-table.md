---
title: "Costing table"
slug: costing-table
source: https://help.paperlessparts.com/s/article/costing-table
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Costing table

> Source: https://help.paperlessparts.com/s/article/costing-table  
> Topic: Pricing, Costing & P3L

Each quote item has a costing table, which you can find below all of its operations and components:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f53be1e2a777301b74337/file-KuOBI3ned8.png)This costing table shows you the total sum money across all of the elements of cost within the quote item. We separate these costs into different cost categories, that we call "colors of money". The different colors of money are raw material, inside processing, outside processing, purchased components, and manufactured component overrides. These are the sum of all dollars across every component, operation, and raw material you have in your quote item, for single component and multiple component quote items. These colors can be described as follows:

- Total Raw Material = the sum of all material operations
- Total Inside Processing = the sum of all operations not marked as an outside service
- Total Outside Processing = the sum of all operations marked as an outside service
- Total Purchased Components = the sum of all total costs associated of purchased components (including overrides to a purchased component's unit cost)
  - Note: This row will not appear if the quote item has a single component (not an assembly)
- Total Manufactured Component Overrides = the difference between the total estimated cost and the sum of all colors of money
  - Note: This row is necessary because you can specify a manual unit cost for manufactured components within an assembly. If you manually override this value, we lose the ability to rigorously break down your costs into different colors of money. As a result, we recommend that you do NOT manually override unit cost for child components, and instead modify costs within operations.
  - Note: This row will not appear if the quote item has a single component (not an assembly)

## Display options

To access display options for the costing table, select the gear in the top right:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f564d1e2a777301b74344/file-7S3F7Sh2Q6.png)

Deselect **Truncate values** to see all costs out to four decimal places rather than two.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6357e1fc4d805871ceaa66ac/file-NIqI9oNRru.gif)

Switching the cell type to **Percent** will allow you to see the breakdowns of colors of money by percent:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f56dc2ce7ed0fb09110f8/file-CKFEuFLrO0.png)

This percent view is very powerful for gaining insight into your costs and preventing mistakes. This is like a mini-analytics tab for your quote item. Here you will be able to quickly notice if you may have missed an input for a certain quantity or if you're getting squeezed with high material or outside processing costs.
