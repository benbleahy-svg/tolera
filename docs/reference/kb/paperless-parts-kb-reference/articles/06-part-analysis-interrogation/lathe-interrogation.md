---
title: "Lathe interrogation"
slug: lathe-interrogation
source: https://help.paperlessparts.com/s/article/lathe-interrogation
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Lathe interrogation

> Source: https://help.paperlessparts.com/s/article/lathe-interrogation  
> Topic: Part Analysis & Interrogation

Paperless Parts has an interrogation module for the turning/lathe process. When a 3D CAD file is uploaded and lathe interrogation is indicated, we will determine important pricing and manufacturability information about the part. This information includes setup suggestions, feature detection, a comprehensive list of manufacturability feedback, and live tooling information if there are features that cannot be machined on a pure lathe.

In addition, the strategy used to determine why certain features are shown is customizeable. Paperless Parts interrogation can be altered to make the module fit the capabilities and workflows of your shop. Every manufacturability warning we detect can be turned on or off, and you can set the thresholds that determine why they are called out in the first place.

Before reading the rest of this page, it is highly recommended that you check out our intros to [P3L](https://help.paperlessparts.com/s/article/pricing-language-p3l) and [lathe-specific P3L.](https://help.paperlessparts.com/s/article/lathe)

# How Customization Works

To customize how the interrogation analyzes a geometry, check out our Custom Interrogations article. In short, for all of these customization elements below, there are one or more corresponding inputs that you can set for a custom interrogation object. If you want any sort of interrogation inputs that are different from the defaults we give, simply adjust the inputs to your desired values. The input editor looks like this for lathe:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e18ad0d2c7d3a7e9ae60b52/file-WTid5owKq8.png)

NOTE: All dimensional inputs are in units of inches

We break down the customization into two sections: strategy and manufacturability analysis. Strategy customization lets the interrogation know how you will manufacture the part. Manufacturability customization tells the interrogation what you want to see in terms of manufacturability warnings. In this document you will learn how to adjust thresholds and even turn off the discovery of certain feedback elements all together if they are not important to your shop.

#

# Strategy Customization

###

### Set Your Tool Dimension Limits

We specify two types of lathe cuts: radial and axial. Radial cuts tend to be on the external surfaces of the part and are made with a tool facing almost perpendicular to the lathe. Axial cuts tend to be on internal surface and are made with a tool oriented parallel to the lathe axis. This distinction is made because of the different tools used for each type of cut.

There are three inputs to tell the interrogation what the limits of your tool crib are. The first specifies the maximum protrusion length of a tool (distance from top to bottom). The others specify the dimensions of hooked tools used for internal grooving and other hard-to-reach features.

#### Corresponding Inputs

- max_tool_protrusion_length: maximum length of a tool. Altering this input changes which faces will be cut by each setup and direction depending on the geometry of the part.
  - Default: 5.0 in (127.0 mm)
- axial_max_hooked_tool_radius: maximum reach for a hooked tool used in an axial cut (axial direction). Measurement is from the diameter of the tool to the tip of the largest protrusion (the area where the material is in contact with the tool).
  - Default: 0.75 in (19.05 mm)
- radial_max_hooked_tool_radius: maximum reach for a hooked tool used in a radial cut (perpendicular direction). Measurement is from the diameter of the tool to the tip of the largest protrusion (the area where the material is in contact with the tool).
  - Default: 0.5 in (12.7 mm)

The image below represents the output of an interrogation where the maximum tool protrusion length was 2 inches instead of the default 5 inches. Faces assigned to each of the two setups changed after this input threshold was altered. Instead of allocating all of the internal faces to the blue setup, the purple setup must machine some of the internal faces to ensure the whole part is cut.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f5ceb04286347867590a8/file-rSQkktuSOG.png)

### Set Your Live Tooling Capability

When features on a lathe part cannot be machined by a turning operation, live tooling is an option. Live tooling is similar to three-axis milling, but the part is fixtured on the lathe. This allows for more volume removal for a given setup along with faster machine direction adjustments compared to putting the part on a traditional mill.

There are three inputs to tell the interrogation what your process can support when it comes to live tooling. The first has the ability to turn off all live tooling capabilities; your interrogation would only provide feedback for traditional turning operations. The others specify which directions (axial or radial) your machine has live tooling capability.

#### Corresponding Inputs

- should_perform_live_tooling: True/False
  - Default: True
- can_perform_axial_live_tooling: True/False
  - Default: True
- can_perform_radial_live_tooling: True/False
  - Default: True

The image below shows which faces are cut from the radial direction (purple) and one of the axial directions (blue).

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f86382c7d3a2ec4bf9398/file-4t2qiiTW0o.png)

#

# Manufacturability Feedback Customization

##

## Lathe

### Work Envelope Size Restrictions

The work envelope, or region of working space, varies widely between machines. Without having to manually reference the size of the part and the size of the machine, this will check the boundaries specified and provide feedback whether there are spacing issues.

#### Relevant Inputs

- max_part_length: length of the machine's work envelope; the maximum length of a part that can be cut on the machine
  - Default: 36"
- max_part_diameter: diameter of the machine's work envelope; the maximum diameter of a part that can be cut on the machine
  - Default: 18"

- should_detect_size_restrictions: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e18b8ba2c7d3a7e9ae60bd1/file-yWBn0hNAgL.png)

### Bored Hole Without Relief Detection

Holes cut with lathe operations use a stationary drill bit. If a bored hole is required in one of these operations, the boring bar must enter the cavity already created by the drilled relief hole. The dimensions of the bored hole is important in determining how much relief (distance between the bore plane and the bottom of the relief hole) is needed. In the image below, the relief distance is 0.1 inches while the diameter of the bored hole is 0.5 inches. The ratio of these two numbers (relief distance / diameter) determines whether the relief distance is sufficient.

Bored holes with ratios less than the specified threshold have a risk of damaging tools due to insufficient spacing.

#### Relevant Inputs

- bore_hole_relief_ratio: minimum ratio of relief distance to diameter for a lathe-bored-hole to have sufficient relief
  - Default: 0.25
- should_detect_bore_hole_wo_relief: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f5fcc2c7d3a2ec4bf91f1/file-dES9AF1XR2.png)

### Slender Part Detection

Lathe parts that are both long and have a small diameter can require special holds or multiple setups due to their lack of structural support from the material. If a part has a large total length to smallest diameter ratio, it is considered slender. The total length is designated by a line and the face with the smallest diameter is highlighted in the partviewer.

#### Relevant Inputs:

- slender_part_ratio: minimum total length to smallest diameter in order for a part to be considered slender
  - Default: 8.0
- should_detect_slender_part: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f68fd0428634786759175/file-v9phGICDiu.png)

### Small Internal Radii Detection

Depending on the tool geometry and direction of the tool with respect to the part, a turning operation is limited by tight corners and small internal radii. An internal edge between two faces can only be so small. By specifying the smallest internal radius your shop can machine, programmers and quoters will have the ability to have these features brought to their attention immediately instead of having to manually search for dimensions.

#### Relevant Inputs

- small_internal_radius_threshold: the smallest internal radius that would not raise a red flag
  - Default: 0.0394 in (1.0 mm)
- should_detect_small_internal_radius: True/False:
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f6aca2c7d3a2ec4bf929e/file-8BzITKsRPJ.png)

### Steep Profile Detection

The angle of external faces (planar and conical) to the lathe axis affects how fast external faces of a lathe part can be machined. Steep profiles tend to take longer to machine and require more specific tools to machine. If this feature changes the way you price and quote, it can help you by showing your quoters the location and angle associated with these features. You can specify the angle threshold that best fits your quoting. In the image below, the threshold was altered to 40 degrees.

NOTE: This feature's defaults are off, so you must specify that you want this feature to be shown.

#### Relevant Inputs

- steep_profile_angle_threshold: minimum angle of a planar or conical external face to the lathe axis for it to be considered a steep profile
  - Default: 1 radian (57.3 degrees)
- should_detect_steep_profile: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f764d2c7d3a2ec4bf92ec/file-Khkslkunyx.png)

##

## Live Tooling

### Tight Corner Detection

Internal corners that are profiled must be radiused due to tool spacing. Without a radius, manufacturing the feature is impossible.

#### Relevant Inputs

- should_detect_tight_corners: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f84932c7d3a2ec4bf9387/file-yaPs6wftPL.png)

### Off Axis Hole Detection

Lathes equipped with live tooling typically only have axial or perpendicular capability. If there is a hole feature that cannot be machined from either of these directions, it is likely that it cannot be machined at all. This process calls out off-axis holes instantly.

#### Relevant Inputs

- should_detect_off_axis_holes: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f84a70428634786759270/file-D5bysgkOJZ.png)

### Asymmetric Cavity Detection

In order to couple with other parts, live-tooling-parts typically have cavities that are symmetric about the lathe axis. When a cavity is not symmetric about the lathe axis, it can be useful to clarify with the designer that the asymmetric geometry is indeed what they are looking for and not a mistake. Additionally, asymmetric cavities tend to have inconsistent tool-to-material contact that can reduce tool life, require slower feed speeds, and cause uneven burrs that are difficult to remove.

#### Relevant Inputs

- should_detect_asymmetric_cavities: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3f84b82c7d3a2ec4bf938d/file-cFuQzyiBeR.png)
