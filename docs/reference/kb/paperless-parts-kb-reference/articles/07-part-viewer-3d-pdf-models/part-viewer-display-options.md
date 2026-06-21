---
title: "3D viewer display options"
slug: part-viewer-display-options
source: https://help.paperlessparts.com/s/article/part-viewer-display-options
topic: "Part Viewer (3D / PDF / Models)"
captured: 2026-06-19
---

# 3D viewer display options

> Source: https://help.paperlessparts.com/s/article/part-viewer-display-options  
> Topic: Part Viewer (3D / PDF / Models)

## Display Options Popover

There are display options you can access through the gear icon in the top right of the part viewer screen:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f49201e2a777301b742fb/file-QhMafvYIs9.png)

Within this menu, you can:

- Toggle the display units of all dimension, area, and volume values between imperial and metric
- Toggle on/off the colors and opacity of the uploaded model with our default values
- Customize measurement decimal precision

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6388ca515ccf77301bc55803/file-jEijXl4A0C.png)

## Toggling Units

With imperial units, the dimensional values presented in the bottom right of the screen, bounding box dimensions, caliper tool measurements, and selection meta data will be in inches. With metric units, these values will be in millimeters. Weight will be given in pounds for imperial and kilograms for metric.

Here is the display for **imperial units**:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f4f7eaf6f8700f6daadbc/file-HbQMu5jLy8.png)

Here is the display for **metric units**:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f4fb2af6f8700f6daadbd/file-P8BkKdVYJS.png)

## Decimal precision

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6388c9f0f4bebb295ed7b971/file-X0cw81oecf.png)

Use the Decimal Precision value to customize the decimal precision of measurements and selection data in the part viewer.

If you're taking extremely precise measurements in the viewer, note that we will indicate if a measurement result is exact versus approximate. When you're taking a measurement between two edges, faces, or vertexes that have similar orientations (e.g. parallel planes, concentric cylinders, perpendicular cylinders and planes, etc.), the measurement will be mathematically *exact*. Any measurements that fall outside of these special cases is approximate, which we'll call out with a ~ symbol:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6388cbc05ccf77301bc55804/file-0aCO0iQGOk.png)

## Toggling Native Model Colors & Opacity

By default, the part will be displayed with the color and opacity of the uploaded model. It is common for STEP files and other proprietary formats to be exported with certain color and opacity settings. Sometimes these colors can conflict with the highlight colors for features like sheet metal bends, holes, countersinks, pockets, etc. In order to better view these feature callouts, you can toggle the color of the model between what is natively stored in the file and our default model color.

Here is a picture of a natively yellow-ish model with all its cutout features highlighted:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f510dab585b230a89c4f5/file-RIijKZpfsl.png)

Now here is that same view with the default colors toggled on:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/621f513eab585b230a89c4f7/file-HgoZbKCzRB.png)

As you can see, the cutout features are much easier to see. Use this color toggle when the native colors from the model make it challenging to see certain features or it provides low contrast with edges.
