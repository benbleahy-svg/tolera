---
title: "Milling interrogation"
slug: milling-interrogation
source: https://help.paperlessparts.com/s/article/milling-interrogation
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Milling interrogation

> Source: https://help.paperlessparts.com/s/article/milling-interrogation  
> Topic: Part Analysis & Interrogation

Paperless Parts has an interrogation module for 3-axis milling. Given a 3D CAD file, we will determine important pricing and manufacturability information about a part. Information our 3-axis interrogation provides includes setup suggestions, feature detection, a comprehensive list of manufacturability feedback, and even estimates of cycle time.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5f0c890404286306f806a924/file-0gCzIl6Mkb.png)

Furthermore, you can customize the interrogation module to fit the capabilities and workflows of your shop. Every manufacturability warning we detect can be turned on or off, and you can set the thresholds that determine whether or not they are called out. We even let you customize aspects of machining strategy.

Before reading this, it is highly recommended you check out our [intro to P3L for milling.](https://help.paperlessparts.com/s/article/three-axis-milling)

# How Customization Works

To customize how the interrogation analyzes a geometry, check out our Custom Interrogations article. In short, for all of these customization elements below, there are one or more corresponding inputs that you can set for a custom interrogation object. If you want any sort of interrogation inputs that are different from the defaults we give, simply adjust the inputs to your desired values. The input editor looks like this for milling.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e18a70004286364bc93bc3f/file-q9hG20aYx3.png)

NOTE: All dimensional inputs are in units of inches.

We break down the customization into two sections: strategy and manufacturability analysis. Strategy customization lets the interrogation know how you will manufacture the part. Manufacturability customization tells the interrogation what you want to see in terms of manufacturability warnings. In this section you can adjust thresholds and even turn off the discovery of certain feedback elements all together if they are not important to your shop.

# Strategy Customization

###

### Set Your Profiling Strategy

A profiled cut occurs when the entirety of the face is perpendicular to the axis of the cutting tool. There are two inputs to tell the interrogation how you would perform a profiling operation/cut. The first is specifying the maximum depth that a profiled cut can be performed. This threshold usually affects outputs by moving faces that would be profiled in an earlier setup to facing operations in a follow-up setup.

#### Corresponding Inputs

- depth_profiling_threshold: maximum profile depth
  - Default: 2.0 in (50.80 mm)

The image below represents the output of an interrogation where the profile depth threshold was 1.1 inches instead of the default 2 inches. This is the same part from the image above. As you can see, the face allocation for the setups is slightly different, where Op1 (purple) only profiles part of some faces and Op2 (dark blue) profiles the remainder of these faces. Additionally now Op3 (yellow) performs a facing operation on the entirety of the face that hosts the countersunk holes. The removal of these volumes from the stock piece influence downstream logic like manufacturability feedback detection and runtimes. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d362b34042863478675467c/file-hcC44qmUaI.png)

### Set Your Surfacing Strategy

A surfaced cut is any face that is cut with a normal at any point that is not perpendicular or anti-parallel to the axis of the cutting tool. Common situations where surfacing is required is with fillets, chamfers, and drafted walls. You can customize both the maximum depth at which any surfaced cut is allowed to be performed and how the surfaced faces influence setup allocation.

#### Corresponding Inputs

- depth_surfacing_threshold: maximum surfaced cut depth
  - Default: 1.80 in (45.65 mm)
- minimum_area_for_setup: If faces can be machined using surfacing operations in an existing setup, but can also be machined using profiling operations in a new setup, this threshold specifies the minimum amount of area in order to add the new setup and cut the faces more efficiently.
  - Default: 1.55 sq. in (1000 sq. mm)

The images below demonstrate the affect of adjusting the `minimum_area_for_setup`. In the second image, the threshold is smaller than the default, so less surface area is needed to allocate a new setup to cut the faces in orange more efficiently.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d36386704286347867546ea/file-yLMNrQzaWz.png)![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d36387604286347867546eb/file-bc3vZ1QC3y.png)

### Set Max Hole Diameter

If a hole has a diameter greater than your specified threshold, it will be called out as a circular pocket and cut with profiling operations instead of drilling operations. The different types of volume removals will influence downstream information like manufacturability warnings and runtimes.

#### Corresponding Inputs

- maximum_hole_diameter
  - Default: 2 in (50.80 mm)

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d363a9d04286347867546f7/file-0qWdVXB4z0.png)

#

# Manufacturability Feedback Customization

### Work Envelope Size Restrictions

The work envelope, or region of working space, varies widely between machines. Instead of having to manually reference the size of the part and the size of the machine it will be milled on, this will check the boundaries specified and provide feedback if there are spacing issues.

#### Relevant Inputs

- max_part_length: length of the machine's work envelope; the maximum length of a part that can be cut on the machine
  - Default: 64"
- max_part_width: width of the machine's work envelope; the maximum width of a part that can be cut on the machine
  - Default: 38"
- max_part_height: height of the machine's work envelope; the maximum height of a part that can be cut on the machine
  - Default: 32"
- should_detect_size_restrictions: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5e18ac6d04286364bc93bc81/file-UsIgBmYg5o.png)

### Deep Hole Detection

Deep holes can be expensive to manufacture because proper chip removal, lubrication, cooling, and tolerances are all difficult to achieve. This will treat sections of a compound hole feature (like a counterbore) individually.

#### Relevant Inputs

- deep_hole_ratio_threshold: minimum cut-depth-to-hole-diameter ratio for a hole to be considered a deep hole
  - Default: 8.0
- should_detect_deep_hole: True/False
  - Default: True

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d363c160428634786754708/file-omBfD5ILQD.png)Deep Radial Cut

A concave face that is profiled which has a cut-depth-to-tool diameter ratio larger than the specified threshold. Milling these faces can be expensive to manufacture because of possible machine vibrations (chatter) and tool deflection which cause inaccurate cuts and shorter tool life. The tool diameter used in the calculation is determined based on the radius of the cylindrical face; only standard tool sizes are considered. If the dimensions of the concave face allow for a tool larger than the specified maximum tool diameter ('max_tool_diameter'), then the max tool diameter value is used instead.

#### Relevant Inputs

- deep_cut_radiused_ratio_threshold: minimum cut-depth-to-tool-diameter ratio for a radiused cut to be considered a deep radial cut or a deep circular pocket.
  - Default: 3.0
- max_tool_diameter: maximum tool diameter used for anything other than facing: mainly profiling operations
  - Default: 0.5 in (12.7 mm)
- should_detect_deep_cut_radiused: True/False
  - Default: True
- should_detect_deep_circular_pocket: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d363e2f2c7d3a2ec4bf4399/file-I1rbLLce0t.png)![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d363e382c7d3a2ec4bf439a/file-bYLkJJTWlL.png)

### Deep Planar Cut

A planar face that is profiled which has a cut-depth-to-tool-diameter ratio larger than the specified threshold. The tool diameter used in the calculation is the max tool diameter. Milling these faces can be expensive to manufacture because of possible machine vibrations (chatter) and tool deflection which cause inaccurate cuts and shorter tool life.

#### Relevant Inputs

- deep_cut_planar_ratio_threshold: minimum cut-depth-to-tool-diameter ratio for a profiled planar face to be considered a deep planar cut
  - Default: 4.0
- max_tool_diameter: maximum tool diameter used for anything other than facing: mainly profiling operations
  - Default: 0.5 in (12.7 mm)
- should_detect_deep_cut_planar: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d363f7c0428634786754718/file-Xr0AfjLR90.png)

### Small Internal Radius

Similar to deep radial cuts, but instead of a depth to tool diameter ratio, this calls out internal rads that are less than a size threshold. This a useful feature for very quick no quotes or prompts to contact the customer for a potential design adjustment.

#### Relevant Inputs

- small_internal_radius_threshold: maximum radius of an internal radius feature
  - Default: 1/32 in (0.79375 mm)
- should_detect_small_internal_radii: True/False
  - Default: True

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3641a80428634786754721/file-ntDeHHXWTU.png)Small Hole Diameter

Calls out holes with diameters smaller than a size threshold. This a useful feature for very quick no quotes or prompts to contact the customer for a potential design adjustment.

#### Relevant Inputs

- small_hole_diameter: minimum diameter of a hole feature
  - Default: 1/16 in (1.5875 mm)
- should_detect_small_hole_diameter: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3642520428634786754726/file-uGUolNyDA4.png)

### Blind Holes

Blind holes are more difficult to manufacture than through holes, especially flat bottom holes, because of increased chip load and difficulty to clear chips with coolant.

#### Relevant Inputs

- should_detect_tipped_hole: True/False
  - Default: True
- should_detect_flat_bottom_hole: True/False
  - Default: True

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3644c50428634786754737/file-UNI0XXdUE9.png)Slanted Hole

if the normal of the entrance or exit surface of a hole deviates from the hole's axis more than the specified threshold, then the hole is considered a slanted hole. These features require extra consideration by the manufacturer. The tool can wander when entering a slanted surface. Exiting a hole through a slanted surface can create non-uniform burrs which are difficult to remove.

#### Relevant Inputs

- slanted_hole_angle_threshold: minimum angle deviation from perpendicular for a hole to be considered slanted
  - Default: 0.035 radians (2 degrees)
- should_detect_slanted_hole: True/False
  - Default: True

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3648512c7d3a2ec4bf43e0/file-Xkvx8l8NBA.png)Partial Hole

Partial holes are hole features that do not have tool contact 360 degrees around the tool for some or all the duration of travel. This inconsistent tool contact to the material can cause burrs to form at the feature edges.

#### Relevant Inputs

- should_detect_partial_hole: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3649082c7d3a2ec4bf43ec/file-XRtx3TBsUj.png)

### Holes Through Cavity

If two or more holes on the same axis can be drilled using the same tool and setup direction but are separated by a cavity they are considered holes though cavity. The purpose of having these features detected is to assist manufacturers quoting and programming the part. These features can be machined from one direction, but this requires inconsistent material-to-tool contact because of the cavity. They can also be machined by adding another setup to drill each hole separately. Both methods have advantages and disadvantages depending on the case, but each require extra planning which makes these features useful to point out.

#### Relevant Inputs

- should_detect_hole_through_cavity: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d36484c2c7d3a2ec4bf43df/file-1yNp24Yhht.png)

### Transition Detection

Transition features like fillets and chamfers can significantly increase the complexity of manufacturing a part. Fillets and chamfers require either surfacing operations or very specific tools to manufacture. It can be difficult to achieve tolerance and desired surface finishes on these transition features, especially if they exist within deep pockets. We callout three separate types of transitions: concave fillets, convex fillets, and chamfers.

#### Relevant Inputs

- should_detect_transitions: True/False
  - Default: True

##### Concave Fillets

##### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3647f20428634786754755/file-WhTWwsVOVk.png)Convex Fillets

##### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3647fe0428634786754757/file-Nt6smSPUAo.png)Chamfers

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d36480e0428634786754758/file-d1sBF4My6G.png)

### Tapered Walls

A tapered wall is a slanted plane that requires surfacing operations. Note: This feature is very similar to a chamfer. These features differ depending on the angle of the face with respect to attack direction and the dimensions of the face (length and height).

#### Relevant Inputs

- should_detect_tapered_walls: True/False
  - Default: True

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3647bc0428634786754753/file-A5SN4BZ6K1.png)

###

### Tight Corners

###

Calls out internal corners that are 90¬∞. This will detect square pockets, which cannot be achieved with traditional round tooling.

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61e9e62e8200bc052eb80f5a/file-xf4iJkmZJG.png)

### Uncut Faces

Calls out faces that are inaccessible using three-axis tooling. These features cannot be manufactured using this process. This cannot be disabled.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d3647a90428634786754752/file-kry0AVoJDm.png)
