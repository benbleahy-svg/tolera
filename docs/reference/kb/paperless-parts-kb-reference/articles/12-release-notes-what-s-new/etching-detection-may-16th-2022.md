---
title: "Etching detection - May 16th, 2022"
slug: etching-detection-may-16th-2022
source: https://help.paperlessparts.com/s/article/etching-detection-may-16th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Etching detection - May 16th, 2022

> Source: https://help.paperlessparts.com/s/article/etching-detection-may-16th-2022  
> Topic: Release Notes (What's New)

## What's new in v24.2.2

Our sheet metal interrogation will now extract etchings from 3D files. The part must properly unfold for detection to work.

Etchings are features that often serve as labels, welding guides, or even QR codes. These features are still performed with a laser cutter, just do not constitute a pierce through the entire thickness of the material. The etchings will be collected into a separate feature class in the geometric features panel of the viewer, as seen below.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6299147de1d2cf0eac00d707/file-o1dF9EFyuX.png)

The length of these etchings can be extracted in your costing formulas through feature iteration. The etching length will not contribute to any existing cut length or traversal length properties you currently have access to from the sheet metal interrogation in your pricing formulas. Take a look at our [sheet metal feature iteration](https://help.paperlessparts.com/s/article/sheet-metal-feature-iteration) documentation for more info.
