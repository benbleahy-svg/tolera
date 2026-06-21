---
title: "Tube laser interrogation"
slug: tube-laser-interrogation
source: https://help.paperlessparts.com/s/article/tube-laser-interrogation
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Tube laser interrogation

> Source: https://help.paperlessparts.com/s/article/tube-laser-interrogation  
> Topic: Part Analysis & Interrogation

Paperless Parts has an interrogation module for the tube laser process. When a 3D CAD file is uploaded and tube laser interrogation is indicated, we will determine important pricing and manufacturability information about the part. This information includes cut length, pierce counts, manufacturability feedback, and stock dimensions.

# Tube Compatibility and Dimensions

The tube laser interrogation supports the five different tube cross sections shown below. The CAD file must match one of these cross sections in order for compatibility to be met. The diagram below also describes the data accessible for each cross section.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63a324c0f439e8768b4f6683/file-CmrcZd1iYE.png)

# How Customization Works

The strategy used to determine why certain features/feedback are shown is customizable. Paperless Parts interrogation can be altered to make the module fit the capabilities and workflows of your shop. Every manufacturability warning we detect can be turned on or off, and you can set the thresholds that determine why they are called out in the first place.

To customize how the interrogation analyzes a geometry, check out our [Custom Interrogations article](https://help.paperlessparts.com/s/article/custom-interrogations). For all of the customization elements discussed in this article, there are one or more corresponding inputs that you can set for a custom interrogation object. If you want any interrogation inputs that are different from the defaults we give, simply adjust the inputs to your desired values. The input editor looks like this for tube laser:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5fa4a3bbcff47e00160b73cd/file-BweyF3wimI.png)

# Strategy Customization

### Set Countersink Strategy

Depending on your tube laser machine's capability, countersinks may be cut with the laser or with additional operations. When it is indicated in your interrogation inputs that countersinks can be lasered, these features will be counted towards total cut length and added to the pierce count. We assume the circumference of the major diameter of the cone (countersink) accurately represents the cut length of these features. When this capability is not indicated, countersinks will still be detected, but they will not count towards total cut length or pierce count.

#### Corresponding Inputs

- should_countersinks_be_lasered: True/False
  - Default: True

# Manufacturability Feedback Customization

### Angled Cut Detection

This feedback item is created when the laser cut angle to the tube axis is non-perpendicular. Cuts like these require additional axis capability with your machine. The thickness of these cuts will also be greater than the standard thickness of the part. This can effect cut speeds and quality of the cut.

Additionally, the maximum angle of cut (in degrees) may be specified. This functionality is especially useful for tube laser machines with limited angled cut functionality. If a cut is detected with an angle that exceeds the specified threshold, the cut will be flagged as an *Additional Operations Required*feedback item (P3L Name: 'machining_required') rather than an *Angled Cut.*

#### Corresponding Inputs

- max_angled_cut_threshold: maximum angle (in degrees) in which a cut can be made on your machine. Any cuts with an angle exceeding this value requires additional operations
  - Default: 45 degrees
- should_detect_angled_cuts: True/False
  - Default: True
- should_detect_angled_cuts_on_round_tubes: True/False
  - Default: False

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f99e883cff47e001a59347f/file-tU8dLln3aU.png)

### Close Cutouts Detection

This feedback item is created when two marked features are closer together than your specified minimum distance ratio. This threshold corresponds to all features that are lasered.

#### Corresponding Inputs

- close_cutouts_threshold: smallest distance ratio (distance to thickness) between two cutout features you can safely manufacture
  - Default: 1.0
- should_detect_close_cutouts: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f99e961c9e77c001621c8e6/file-m4x7tPUZdC.png)

### Cutouts Close To Edge

When a cutout feature is closer to the material edge than your specified minimum distance ratio, this feedback instance will show up.

#### Corresponding Inputs

- cutout_edge_proximity: smallest distance ratio (distance to thickness) between a cutout feature and the material edge you can safely manufacture
  - Default: 2.0
- should_detect_cutout_edge_proximity: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f99e8a746e0fb0017991c22/file-TdTlADE72M.png)

### Close Countersinks Detection

This feedback item is created when two countersink features are closer together than your specified minimum distance ratio.

#### Corresponding Inputs

- close_countersinks_threshold: smallest distance ratio (distance to thickness) between two countersinks you can safely manufacture
  - Default: 8.0
- should_detect_close_countersinks: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f99e8c0cff47e001a593481/file-y0kwGT0GnR.png)

### Countersinks Close To Edge

When a countersink feature is closer to the material edge than your specified minimum distance ratio, this feedback instance will show up.

- countersink_edge_proximity_threshold: smallest distance ratio (distance to thickness) between a countersink and the material edge you can safely manufacture
  - Default: 4.0
- should_detect_countersink_edge_proximity: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f99e8d1c9e77c0016754835/file-uolFoQJHcn.png)
