---
title: "Sheet metal interrogation"
slug: sheet-metal-interrogation
source: https://help.paperlessparts.com/s/article/sheet-metal-interrogation
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Sheet metal interrogation

> Source: https://help.paperlessparts.com/s/article/sheet-metal-interrogation  
> Topic: Part Analysis & Interrogation

Paperless Parts has a very robust interrogation module for sheet metal parts. It is also fully customizable to the characteristics of your shop and your capabilities.

Before reading this, it is highly recommended that you check out our [intro to P3L for sheet metal](https://help.paperlessparts.com/s/article/sheet-metal-process).

The appearance of certain features and manufacturability feedback items will be determined by the inputs you give to the analysis request `analyze_sheet_metal()`

Our interrogation will take a CAD file and identify all bends, along with all the necessary pricing information about them (length, angle, radius, etc.). From these bends, the interrogation will then unfold the part to extract important pricing parameters like the unfolded dimensions and the thickness. The interrogation will also identify all marked features and commonly requested features like countersinks and counterbores.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3207512c7d3a2ec4bf20ca/file-vTWCwCDWrb.png)

The presentation of the marked features and manufacturability analysis performed on the geometry depends on what type of interrogation recipe you specify. The interrogation can be flavored to mirror a contour cutting machine (like a laser cutter, water jet, or plasma cutter), a punch machine, or a punch-laser machine. Based on which flavor you select, we will adjust how we present marked features in the partviewer and what thresholding we apply for manufacturability analysis.

The numerical values required for pricing all three types of machines will always be populated regardless of which interrogation flavor you have selected, so at quote time, you do not necessarily have to price to an individual machine.

## How Customization Works

To customize how the interrogation analyzes a geometry, check out our Custom Interrogations article. In short, for all of these customization elements below, there are one or more corresponding inputs that you can set for a custom interrogation object. If you want any sort of interrogation inputs that are different from the defaults we give, simply adjust the inputs to your desired values. The input editor looks like this for sheet metal:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5db9d6802c7d3a7e9ae34407/file-TNyn0OCxaG.png)

We break down the customization into two sections: strategy and manufacturability analysis. Strategy customization lets the interrogation know how you fundamentally will manufacture the part. Manufacturability customization tells the interrogation what you want to see in terms of manufacturability warnings. In this section you can adjust thresholds and even turn off the discovery of certain feedback elements all together if they are not important to your shop.

## Strategy Customization

### Pick your marking machine type

Select which type of machine you will use to mark your sheet metal parts. You can choose a contour-cutting type machine (laser cutter, water jet, plasma cutter), a punch machine, or a machine that combines both punching and contour cutting, like a punch-laser. The selection of this machine type will drive what types of features are called out in the partviewer.

#### Corresponding Inputs

- is_laser: True/False (Default: True)
- is_punch: True/False (Default: False)
- is_punch_laser: True/False (Default: False)

The selection of these different types of strategies will affect how features are called out. If the laser strategy is selected, marked features will be identified as cut out features. If the punch strategy is selected, marked features will be identified as a collection of single-hit punch features (circular, obround, rectangular, square, and slot shapes) and multi-hit punch features. If punch-laser is selected, marked features will be identified as a collection of single-hit punch features and cut out features. Below illustrates how we will call out different types of marked features based on machine type

#### Laser

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f60f55dc9e77c00160395d0/file-tHrY29FoQr.png)

####

####

#### Punch

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f60f5ab4cedfd00173b82e2/file-bdLah1X5Fa.png)

### Punch-Laser

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f60f5c3c9e77c00160395d4/file-Lbo3tqDqyj.png)

#### Single-Hit Dimensions

##### NOTE: for a feature to be considered a single-hit feature, the contour must have characteristically simple geometry. It must be a circle, square, rectangle, slot, or obround feature.

#####

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f610c28c9e77c0016039681/file-QJj80wjvLI.png)

After establishing which flavor of interrogation you want, you can customize several inputs that drive pricing and manufacturability analysis outputs.

### Pick your marking size thresholds

Establish what is the smallest size of a marked feature you would manufacture. For punching, establish what is the largest simple geometric contour you would punch with a single hit.

#### Corresponding Inputs

- smallest_cutout_size: Smallest marked feature you could remove with your machine as a multiple of material thickness
  - Default for laser type: 1.0
  - Default for punch type: 1.0
  - NOTE: if a simple hole feature has a diameter smaller than this threshold, it will be recorded as a manual simple drilled hole, requiring a secondary manual operation. This cut length will not be populated to the cut length tracking for punch features and pierced features
- single_hit_max_size_threshold: Largest dimension of a simple contour feature that would be cut with a single hit from a punch tool
  - Default: 6 in

### How we determine K factor value

The k-factor is an empirical constant that describes how much the neutral axis of a bend will shift due to plastic deformation when bending. This plastic deformation results in the effective elongation of the material. K factor values vary with material, bend thickness, and bend radius, so we use an equation to approximate the K factor across all geometries. The formula we use is

```
 k = (BASE_K_FACTOR + 0.5 * math.log10(radius / thickness)) * 0.5
```

The base k-factor we use is 0.65. This leads to textbook outputs for bend k-factors for steel-type materials. This currently is NOT configurable. While a change in base k-factor can result in slightly different sizes in unfolded parts, that level of detail complicates quoting workflows. For quoting purposes, this base formula results in accurate unfolding results to get reliable material utilization regardless of material type.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e3080662c7d3a7e9ae6de24/file-BUxm67eaAN.png)

### Pick your offset height threshold

Establish what is the largest offset height (seen above) that can be formed with one punch and die. Bends with a larger offset height will be split up into two independent bends.

#### Corresponding Inputs

- max_offset_height: Maximum offset distance between two opposite bends to be considered an offset instead of two independent bends.
  - Default: 1/4"
- should_detect_offsets: True/False
  - Default: True

###

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6001dca7c64fe14d0e1fb671/file-LONH57ELMl.png)

### Pick your press working length

Establish the maximum working length of your press. Bends longer than this length will be highlighted for feedback.

- press_length: Bends longer than this length will be highlighted. Bend sections along the same axis will not be combined into bends longer than this length.
  - Default: 20'

## Manufacturability Feedback Customization

### Small Cut Detection

When a marked feature is smaller than your specified minimum feature size. This threshold will also determine whether simple holes must be drilled by hand or cut with the punch or laser. These will populate as simple drilled hole objects and contribute to tracking of hole setups.

#### Relevant Inputs

- smallest_cutout_size: smallest feature size you can cut with a laser/water jet/plasma cutter as a multiple of material thickness
  - Default for laser: 1.0
  - Default for punch: 1.0
- should_detect_small_cuts: Flag to call out small cutouts as manufacturability issues
  - Default: True
  - NOTE: even if this is False, the drilled simple hole logic will still persist. We simply will not call them out in context with the geometry.
- should_count_drilled_holes_as_feedback: If, True, all drilled holes (countersinks, counterbores, simple drilled holes) will be called out as manufacturability issues
  - Default: False

#### Small cut

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31eb06042863478675226d/file-LLdu6hk09D.png)

#### Simple drilled hole

#### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31eb1b2c7d3a2ec4bf1d62/file-MFLSGCB7Fr.png)

### Close Cutouts Detection

When two marked features are closer together than your specified minimum clearance size. This threshold corresponds to all features that span the entirety of the thickness of the part (laser cuts, single hit punches, multi hit punches, and simple drilled holes). Does not correspond to distances between partial hole features such as countersinks and counterbores.

#### Relevant Inputs

- close_cutouts_threshold: smallest gap size between two cut out features you can safely manufacture as a multiple of material thickness
  - Default for laser/water jet/plasma: 1.0
  - Default for punch: 2.0
- should_detect_close_cutouts: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31eb502c7d3a2ec4bf1d65/file-k6aOQTaoaZ.png)

### Cutouts Close To Edge

When a marked feature is closer to the material edge than your specified minimum distance. Smaller gaps found in parts than the default threshold could lead to local deformations of the part and inconsistent shearing operations.

#### Relevant Inputs

- cutout_edge_proximity: smallest gap size between cut out feature and material edge you can safely manufacture as a multiple of material thickness
  - Default for laser/water jet/plasma: 2.0
  - Default for punch: 2.0
- should_detect_cutout_edge_proximity: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ec782c7d3a2ec4bf1d7e/file-cmiyhIlnMl.png)

###

### Close Countersinks/bores Detection

When two countersinks/bores are closer than your specified minimum edge to edge distance. When two of these features are close together, the localized structural integrity of the material could be compromised, resulting in tears and/or undesired deformations.

#### Relevant Inputs

- countersink_bore_proximity_threshold: minimum edge to edge distance as a multiple of material thickness
  - Default: 8.0
- should_detect_close_countersink_bores: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ec882c7d3a2ec4bf1d7f/file-0jLSBKP6tM.png)

###

### Countersink/bore Close to Edge

When a countersink or counterbore is less than your specified minimum edge to material outer edge distance.

#### Relevant Inputs

- countersink_bore_edge_proximity_threshold: minimum countersink edge to material outer edge distance as a multiple of material thickness
  - Default: 4.0
- should_detect_countersink_bore_edge_proximity: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ec93042863478675227e/file-lMOVrekBQd.png)

### Tight Corners

Detect corners with discontinuities in contours from connecting faces.

#### Relevant Inputs

- should_detect_tight_corners: True/False
  - Default: False

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31eca02c7d3a2ec4bf1d81/file-kdNygz6NhM.png)

### Cut Near Bend

When any internal cut out feature is less than your specified minimum distance from a bend. Features too close to a bend can deform and lose their shape when forming.

#### Relevant Inputs

- cut_near_bend_threshold: The multiple of material thickness plus the radius of the bend that determines when a cutout feature is too close to a bend and could cause deformation.
  - Default: 3.0
- should_detect_cut_near_bend: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ecb72c7d3a2ec4bf1d84/file-13g1FVSYXm.png)

### Tight Curl Detection

When a curled feature has a radius less than the specified threshold. Any curl with a radius smaller than the recommended default is difficult to manufacture because of tooling requirements and accessibility issues.

#### Relevant Inputs

- tight_curl_threshold: The multiple of material thickness that determines the minimum outer radius for a curled feature.
  - Default: 2.0
- should_detect_tight_curls: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31eccd2c7d3a2ec4bf1d85/file-GdO4j28UWB.png)

### Curl Near Bend

The multiple of material thickness plus bend radius plus curl radius that determines the minimum distance from the outside of the curl to the bend. Curls very close to bends can be difficult to manufacture for accessibility reasons.

#### Relevant Inputs

- curl_near_bend_threshold: Multiple of material thickness applied to the above ratio
  - Default: 5.0
- should_detect_curl_near_bends: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ecdb2c7d3a2ec4bf1d87/file-49OdWkdncO.png)

### Tight Hem

When a hem diameter is too small, it cannot be manufactured reliably without the risk of undesired tears or deformations.

#### Relevant Inputs

- tight_hem_threshold: The multiple of material thickness that determines the minimum diameter for a hem
  - Default: 1.0
- should_detect_tight_hems: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ed220428634786752283/file-WR7BSl7M2F.png)

### Short Hem Return

When a hem return is not long enough, it is difficult to complete the hemming operation as there is very limited space for the press to make good contact with the material.

#### Relevant Inputs

- short_hem_threshold: The multiple of material thickness that determines the minimum return flange height.
  - Default: 4.0
- should_detect_short_hems: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ed370428634786752284/file-CBpM0ShiW0.png)

### Hem Near Bend

If a hem is too close to a bend, it can be difficult to manufacture for accessibility reasons.

#### Relevant Inputs

- hem_near_bend_threshold: The multiple of material thickness plus bend radius that determines the minimum distance from the return flange of the hem to the bend.
  - Default: 5.0
- should_detect_hem_near_bends: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ed502c7d3a2ec4bf1d8a/file-Ii1e2JCX3Q.png)

### Bend Radius Issues

Bends with a radius that are either greater than or less than your specified limits for bend radii relative to material thickness. Radii that are too small can cause fracturing/cracking (the "orange peel" effect) at the bend site, especially in harder materials. Radii that are too large will result in a spring back effect that will make it very difficult to achieve any sort of tolerance.

#### Relevant Inputs:

- max_bend_radius: Maximum bend radii expressed as multiple of material thickness.
  - Default: 150
- should_detect_large_bend_radius: True/False
  - Default: True
- min_bend_radius: Minimum bend radius expressed as multiple of material thickness.
  - Default: 0.75
- should_detect_small_bend_radius: True/False
  - Default: True

#### Small bend radius

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ed7b2c7d3a2ec4bf1d8f/file-sVerCLoo81.png)

#### Large bend radius

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ed8b2c7d3a2ec4bf1d90/file-FKKVJc1bGv.png)

### Bend Relief Issues

Bend reliefs are small cutouts on the ends of flanges that help prevent the material from tearing or deforming when forming a bend. Detects the presence of no bend relief, thin bend reliefs, and short bend reliefs.

#### Relevant Inputs

- should_detect_bend_relief_issues: True/False
  - Default: True
- thin_bend_relief_threshold: Thin bend relief cut threshold as multiple of material thickness.
  - Default: 1.5
- shallow_bend_relief_threshold: Shallow bend relief threshold as multiple of material thickness plus bend radius.
  - Default: 2.0

#### No Bend Relief

#### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31edac2c7d3a2ec4bf1d92/file-Ft5z8rzm8g.png)

#### Thin bend relief

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31edc32c7d3a2ec4bf1d94/file-CxZsVDun62.png)

#### Shallow bend relief

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31edd20428634786752289/file-HsqSY9tOE5.png)

### Short Flange

Press tools can leave impression marks on bends that are too short, making it hard to achieve tolerance and consistency.

#### Relevant Inputs

- min_flange_length: Minimum flange/bend length as a multiple of material thickness.
  - Default: 4.0
- should_detect_short_bends: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31edf22c7d3a2ec4bf1d97/file-fJga8JztdN.png)

### Abnormal Bend Angle

Call out bends that are other than 90 degrees (excludes hems and curls).

#### Relevant Inputs

- should_detect_non_ninety_bends: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ee122c7d3a2ec4bf1d9b/file-ZB0sVAuwwb.png)

### Different Bend Directions

Bends that must be formed in different directions on the same plane are difficult to manufacture because it is challenging to set them up in a press.

#### Relevant Inputs

- should_detect_different_bend_directions: True/False
  - Default: True

[![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31ee2c0428634786752293/file-XqYdiyMUeH.png)](https://drive.google.com/open?id=1xs-m6W6Jrwr0xhN3B24SuLHML_ziB79B)

### Split Bends

Calls out bends composed of multiple distinct bend sections that can be formed from the same press brake operation.

- should_detect_split_bends: True/False
  - Default: False
- can_split_die: Whether or not the press brake die can be split to hit distinct bends with an obstruction between them (True/False)
  - Default: False

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6001df9b2e764327f87bf2dc/file-4FmzcUidsQ.png)

### Short Flange

Calls out flanges that have a length below the specified short_flange_threshold.

- should_detect_short_flanges: True/False
  - Default: True
- short_flange_threshold: Maximum length to thickness ratio to trigger the warning
  - Default: 1.0

![](https://lh6.googleusercontent.com/D8U5QEZyNTluheMqr2znS3vPtOBKTMRpMo0Ql-XQJhZaEM5dtAzuSLuoxUJKUpLQIQyzgPRjKkTvdVQw37-cksFgDfWHZiSC9wVjJLZW1zXYtPd2vfp5BPrTs778ltNDODLhtjcSbdsF_jGioHZD6u4)

### Close Bends

Calls out parallel bends that are close together on the sheet metal part. The bends can either have the same (U-shape) or opposite (Z-shape) orientation. The warning will trigger if the bend separation to thickness ratio is less than the threshold depending on the orientation. The bends must both be 90 degrees +- 15.

- should_detect_close_bends: True/False
  - Default: True
- close_bends_same_orientation_threshold: Maximum bend separation to thickness ratio to trigger the warning for bends with the same orientation
  - Default: 1.0
- close_bends_opposite_orientation_threshold: Maximum bend separation to thickness ratio to trigger the warning for bends with the opposite orientation
  - Default: 1.0

![](https://lh6.googleusercontent.com/kdOydGYuIAF0ndgZgQYx8TDbjriK2v6HV-Dnkkm2Bs3esWS5a_8rFjjtx_a0m7U2XPJ7x9UgHe8SeH5GE1GdRKZDKiocd7wzWs_2aB0Dy_JcMd6CubI-XtwU3O6tLru7z74qzOxlL4y57ffXKzUO6QI)

### W-Bending May be Required

Calls out whether W-bending, also known as “back bending”, might be needed to form a deep U shape. This warning is triggered if the length to bend separation ratio is greater than the w_bending_threshold. The length is the smaller length of the two legs of the U and the bend separation is the distance between the bends.

- should_detect_w_bending: True/False
  - Default: True
- w_bending_threshold: Minimum length to bend separation ratio to trigger the warning
  - Default: 1.0

![](https://lh3.googleusercontent.com/I_x5I7Bb6k4e8RXN5P5L4--pes94qRfUsQlN_eFFley-WNA_w-qN_-6ZAuR6CTxeOfmQB_p5Wu9ojz123_ILf6MUk5lb8bKWZZQu6rZ2PHz3Y5TPoGWShiozRMZD3b8VTRVXQLU57mkkL-93CPXIXCM)

### Additional Operations Required

Calls out any faces that cannot be hit with traditional tooling or secondary drilling operations. This cannot be disabled.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d31f7d02c7d3a2ec4bf1fde/file-PJvqdxNR8F.png)

### Exceeds Press Length

Calls out bends that have a length that exceeds the press length

- press_length
  - Default: 240 in

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/612e53a06c65aa15b87d5e58/file-AVTsL11gGq.png)

### Dimensions Exceed Limits

Calls out whether folded or unfolded part is too large given size restrictions

- should_detect_size_restrictions: True/False
  - Default: True

#### Folded

- max_length
  - Default: 144 in
- max_width
  - Default: 144 in
- max_height
  - Default: 144 in

#### Unfolded

- max_unfolded_length
  - Default: 144 in
- max_unfolded_width
  - Default: 144 in

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/612e571d2b380503dfdecc62/file-Ccvqw2zqDG.png)

#

## Need Help with Customization? Want More?

Send us an e-mail at support@paperlessparts.com, or use the chat on our website if you have any questions, comments, or requests!
