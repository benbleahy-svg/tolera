---
title: "Milling feature iteration"
slug: milling-feature-iteration
source: https://help.paperlessparts.com/s/article/milling-feature-iteration
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Milling feature iteration

> Source: https://help.paperlessparts.com/s/article/milling-feature-iteration  
> Topic: Part Analysis & Interrogation

For milling processes, a good approach to figuring out runtimes and cost is to break a part down into its features. Once you break down the part into features, you cost each individual feature, and then the total cost just becomes the summation of all individual feature costs. This is exactly what we set out to enable our customers to do with milling feature and feedback iteration.

Our milling interrogation is able to detect a percentage of volume removal with parameterized 2.5D features. We will break down a part into machine directions (or setups for three axis milling), and then break down each setup into individual features (holes, pockets, etc.). For straightforward three axis parts, that volume removal percentage we can detect is usually above 80%. However, for more complicated, perhaps 3+ axis parts, the percentage of volume removal we parameterized with features is smaller. Our geometry team is always seeking to improve our feature classification and detection, so we can push that volume removal percentage higher and higher to allow for more complete feature-based costing.

In this article, we will break down all of the features and manufacturability feedback types extracted by our milling interrogation, as well as tell you how to access and use this information in examples. The cheat sheet below contains all the high level information you will need to get started. For more specifics on what each feature and feedback instance represents, check out our [milling interrogation article](https://help.paperlessparts.com/s/article/milling-interrogation).

```
mill = analyze_mill3()  # request interrogation

# access all features from top level object (features that do not belong to a setup AND features that belong to individual setups)
all_features = get_features(mill)
# access machine directions (only feature in top level object not found in
for feature in get_features(mill):
  feature.properties
  do_something = 1

# access all feedback from top level (feedback that do not belong to any setup AND feedback that belong to individual setups)
all_feedback = get_feedback(mill)
# these can be one of these three: uncut_faces, partially_cut_face, and milling_large_part
for feedback in get_feedback(mill):
  feedback.name
  feedback.type
  feedback.properties
  do_something = 1

# iterate through milling setups
for setup in get_setups(mill):
  # iterate through features in a setup
  for feature in get_features(setup):
    do_something = 1

  # iterate through feedback in a setup
  for feedback in get_feedback(setup):
    do_something = 1

  # iterate through a specific name of features
  for pocket in get_features(setup, name='pocket'):
    pocket.properties.volume
    do_something = 1

  # iterate through a specific name of feedback
  for deep_cut_radius in get_feedback(setup, name='deep_cut_radius'):
    deep_cut_radius.properties.depth_to_tool_diameter
    do_something = 1

# iterate through setups directly from dot operator, returning a copy of p3l list object
for setup in iterate(mill.setups):
  do_something = 1

# access setup features and feedback when using a CNC style process
setup = mill.setups[INDEX]
for feature in get_features(setup):
  do_something = 1
for feedback in get_feedback(setup):
  do_something = 1

# get total count of feature type using len()
count_of_pockets = len(get_features(setup, name='pocket'))
# get total count of feedback type using len()
count_deep_holes = len(get_feedback(setup, name='deep_hole'))

# interact with features and feedback directly from dot operator, returning copies of p3l list objects
# can manipulate these with p3l list functions and methods
features = mill.features.filter(lambda x: x.name == 'pocket').filter(lambda x: x.properties.volume > 0.5).sort(lambda x: -x.properties.volume)
for pocket in iterate(features):
  do_something = 1

for feedback in iterate(mill.feedback):
  do_something = 1
```

### Feature Reference

##### From mill setup

| **Name** (description) | **Properties** (description) |
| --- | --- |
| **machine_direction**(direction machine will approach cutting faces) | **area** (area of all faces cut in setup), **profiled_area** (area parallel to setup direction), **derived_area** (area perp to setup direction), **surfaced_area** (area neither par or perp to setup direction) |
| **circular_pocket** (potentially compound hole-like objects larger than max hole diameter) | **area**, **volume**, **depth**, **bottom_type** (flat, tipped, thru, obstructed), **min_radius** (min rad found in compound feature) |
| **hole** (potentially compound hole features occupying a single hole axis) | **area**, **volume**, **depth**, **bottom_type** (flat, tipped, thru, obstructed), **min_radius** (min rad found in compound feature) |
| **machined_counter_bore** (singular counterbore objects in a hole feature) | **area**, **volume**, **depth** (absolute), **local_depth**, **diameter**, **bottom_type** (flat, tipped, thru, obstructed) |
| **machined_counter_sink** (singular countersink objects in a hole feature) | **area**, **volume**, **depth** (absolute), **local_depth**, **major_diameter**, **minor_diameter**, **semi_angle**, **bottom_type** |
| **machined_simple_hole** (singular simple hole objects in a hole feature) | **area**, **volume**, **depth** (absolute), **local_depth**, **diameter**, **bottom_type** (flat, tipped, thru, obstructed) |
| **pocket** (2.5D feature with walls par to setup direction) | **area**, **volume**, **max_depth**, **bottom_type** (flat, thru, round), **has_transition** (True/False has chamfers or fillets) |

### Feedback Reference

##### From top level `analyze_mill3()` object

| **Name** | **Level** | **Properties** |
| --- | --- | --- |
| milling_large_part | complete_exclusion | n/a |
| partially_cut_face | manufacturing_issue | n/a |
| uncut_faces | manufacturing_issue | n/a |

##### From mill setup

| **Name** | **Level** | **Properties** |
| --- | --- | --- |
| chamfer | cost_driver | area |
| concave_fillet | cost_driver | area, min_radius |
| convex_fillet | cost_driver | area, min_radius |
| deep_circular_pocket | cost_driver | depth, depth_to_tool_diameter |
| deep_cut_planar | cost_driver | depth, depth_to_tool_diameter |
| deep_cut_radius | cost_driver | depth, depth_to_tool_diameter |
| deep_hole | cost_driver | depth, depth_to_tool_diameter |
| flat_bottom_hole | cost_driver | n/a |
| hole_through_cavity | cost_driver | n/a |
| partial_hole | cost_driver | n/a |
| slanted_hole | cost_driver | angle |
| small_hole_diameter | manufacturing_issue | diameter |
| small_internal_radius | manufacturing_issue | radius |
| tapered_wall | cost_driver | area |
| tight_corner | manufacturing_issue | angle |
| tipped_hole | cost_driver | n/a |

### Examples

#### Basic

The example below is a basic usage of feedback iteration to develop a part complexity metric based on the appearance of certain manufacturability feedback. **Note**: take a look at our [custom interrogations article](https://help.paperlessparts.com/s/article/custom-interrogations) to figure out how to customize your feature and feedback outputs.

```
units_in()
mill = analyze_mill3()

# define part complexity dynamic variable, level 1, 2, or 3
complexity = var('Complexity', 1, 'Part complexity based on mfg feedback', number, frozen=False)

# if there are any transition features (fillet, tapered walls, chamfers)
# the part is at least a level 2
for setup in get_setups(mill):
  has_chamfers = len(get_feedback(setup, name='chamfer')) > 0
  has_conc_fillets = len(get_feedback(setup, name='concave_fillet')) > 0
  has_conv_fillets = len(get_feedback(setup, name='convex_fillet')) > 0
  has_tapers = len(get_feedback(setup, name='tapered_wall')) > 0
  has_transitions = has_chamfers or has_conc_fillets or has_conv_fillets or has_tapers
  if has_transitions:
    complexity.update(2)
    break

# if count of deep features is greater than a certain level
# it will be a level 2 or level 3
num_deep_features = 0
for setup in get_setups(mill):
  num_deep_features += len(get_feedback(setup, name='deep_cut_radius'))
  num_deep_features += len(get_feedback(setup, name='deep_cut_planar'))
  num_deep_features += len(get_feedback(setup, name='deep_circular_pocket'))
  num_deep_features += len(get_feedback(setup, name='deep_hole'))

if 10 <= num_deep_features < 25:
  complexity.update(2)
elif num_deep_features >= 25:
  complexity.update(3)

# if the part has a size issue, automatically level 3
if len(get_feedback(mill, name='milling_large_part')) > 0:
  complexity.update(3)

# freeze complexity so overrides can be applied before workpiece
complexity.freeze()

# now store the part complexity in the workpiece for usage in downstream operations
set_workpiece_value('complexity', complexity)

PRICE = 0
DAYS = 0
```

#### Advanced

The example below uses volume removal rates that correspond to certain material families and feature characteristics. If a feature is deeper than a certain threshold, volume removal rates will decrease. **Note**: Here we are iterating through machined_simple_hole, machined_counter_bore, and machined_counter_sink objects directly and NOT hole objects themselves. Hole features are actually potentially compound features that describe any collection of simple holes, counter sinks, and counter bores that lie on the same hole axis. By iterating through the individual sub features of all the hole features we can get more granular with our runtime estimates. It is also important to note that circular_pocket objects can also be compound features, representing any hole-like features (countersinks, counterbores, simple holes) that have a diameter larger than the maximum hole diameter you specify in your custom interrogation. You will likely use a more time consuming volume removal strategy (such as heliboring) to accomplish circular pockets as opposed to simply drilling holes.

```
units_in()
mill = analyze_mill3()

# create removal rate lookup tables based on material family, feature type, and depths
# units of cubic inches per minute
hole_removal_rates = {
  'Aluminum': {
    'shallow': 20,
    'deep': 7.5,
  },
  'Stainless Steel': {
    'shallow': 7,
    'deep': 2.5,
  },
  'Steel': {
    'shallow': 10,
    'deep': 3.75,
  },
}
countersink_removal_rates = {
  'Aluminum': {
    'shallow': 15,
    'deep': 5,
  },
  'Stainless Steel': {
    'shallow': 5,
    'deep': 2,
  },
  'Steel': {
    'shallow': 7,
    'deep': 3,
  },
}
circular_pocket_removal_rates = {
  'Aluminum': {
    'shallow': 15,
    'deep': 5,
  },
  'Stainless Steel': {
    'shallow': 5,
    'deep': 2,
  },
  'Steel': {
    'shallow': 10,
    'deep': 3,
  },
}
pocket_removal_rates = {
  'Aluminum': {
    'shallow': 13,
    'deep': 5,
  },
  'Stainless Steel': {
    'shallow': 4,
    'deep': 2,
  },
  'Steel': {
    'shallow': 8,
    'deep': 3,
  },
}

deep_hole_thresh = 8  # depth to diameter
deep_pocket_thresh = 3  # depth to tool diameter
# assume half inch tool diameter for roughing purposes
pocket_tool_diameter = 0.5
# if hole bottom type is obstructed or flat, we cannot use a drill bit, and will cut slower
# multiply runtime from these holes by a factor
obstructed_bottom_factor = 1.2
# if pocket has transition, apply a runtime muliplier
transition_multiplier = 1.4

if part.material_family in hole_removal_rates:
  hole_ref = hole_removal_rates[part.material_family]
  countersink_ref = countersink_removal_rates[part.material_family]
  circ_pocket_ref = circular_pocket_removal_rates[part.material_family]
  pocket_ref = pocket_removal_rates[part.material_family]
else:
  # if unknown material family, predict for worst case scenario
  hole_ref = hole_removal_rates['Stainless Steel']
  countersink_ref = countersink_removal_rates['Stainless Steel']
  circ_pocket_ref = circular_pocket_removal_rates['Stainless Steel']
  pocket_ref = pocket_removal_rates['Stainless Steel']

# establish tracking variables for hole and pocket runtime
hole_minutes = 0
pocket_minutes = 0
# tracking value for volume removed from features
tracked_volume = 0

for setup in get_setups(mill):
  # runtime logic for simple holes
  for simple_hole in get_features(setup, name='machined_simple_hole'):
    tracked_volume += simple_hole.properties.volume
    depth_ratio = simple_hole.properties.depth / simple_hole.properties.diameter
    is_deep_hole = depth_ratio > deep_hole_thresh or is_close(depth_ratio, deep_hole_thresh)
    if is_deep_hole:
      base_runtime = simple_hole.properties.volume / hole_ref['deep']
    else:
      base_runtime = simple_hole.properties.volume / hole_ref['shallow']

    # now based on bottom type, apply multiplier
    if simple_hole.properties.bottom_type == 'flat' or simple_hole.properties.bottom_type == 'obstructed':
      base_runtime *= obstructed_bottom_factor

    # now add to total runtime tracker
    hole_minutes += base_runtime

  # runtime logic for counterbores, which by definition, are simple holes with obstructed bottom types
  for counterbore in get_features(setup, name='machined_counter_bore'):
    tracked_volume += counterbore.properties.volume
    depth_ratio = counterbore.properties.depth / counterbore.properties.diameter
    is_deep_hole = depth_ratio > deep_hole_thresh or is_close(depth_ratio, deep_hole_thresh)
    if is_deep_hole:
      base_runtime = counterbore.properties.volume / hole_ref['deep']
    else:
      base_runtime = counterbore.properties.volume / hole_ref['shallow']

    # since we know by definition counterbores have obstructed bottoms, multiply by factor
    base_runtime *= obstructed_bottom_factor

    # now add to total runtime tracker
    hole_minutes += base_runtime

  # runtime logic for countersinks
  for countersink in get_features(setup, name='machined_counter_sink'):
    tracked_volume += countersink.properties.volume
    depth_ratio = countersink.properties.depth / countersink.properties.major_diameter
    is_deep_hole = depth_ratio > deep_hole_thresh or is_close(depth_ratio, deep_hole_thresh)
    if is_deep_hole:
      hole_minutes += countersink.properties.volume / countersink_ref['deep']
    else:
      hole_minutes += countersink.properties.volume / countersink_ref['shallow']

  # runtime logic for circular pockets
  for circ_pocket in get_features(setup, name='circular_pocket'):
    tracked_volume += circ_pocket.properties.volume
    depth_ratio = circ_pocket.properties.depth / pocket_tool_diameter
    is_deep_pocket = depth_ratio > deep_pocket_thresh or is_close(depth_ratio, deep_pocket_thresh)
    if is_deep_pocket:
      pocket_minutes += circ_pocket.properties.volume / circ_pocket_ref['deep']
    else:
      pocket_minutes += circ_pocket.properties.volume / circ_pocket_ref['shallow']

  # runtime logic for pockets
  for pocket in get_features(setup, name='pocket'):
    tracked_volume += pocket.properties.volume
    depth_ratio = pocket.properties.max_depth / pocket_tool_diameter
    is_deep_pocket = depth_ratio > deep_pocket_thresh or is_close(depth_ratio, deep_pocket_thresh)
    if is_deep_pocket:
      base_runtime = pocket.properties.volume / pocket_ref['deep']
    else:
      base_runtime = pocket.properties.volume / pocket_ref['shallow']

    # if pocket has transition, apply runtime multiplier
    if pocket.properties.has_transition:
      base_runtime *= transition_multiplier

    # now add to total runtime tracking
    pocket_minutes += base_runtime

# create dynamic variables and freeze them for operation overrides
hole_runtime = var('Hole RT', 0, 'Minutes of runtime for holes', number, frozen=False)
pocket_runtime = var('Pocket RT', 0, 'Minutes of runtime for pockets', number, frozen=False)
hole_runtime.update(round(hole_minutes, 3))
pocket_runtime.update(round(pocket_minutes, 3))
hole_runtime.freeze()
pocket_runtime.freeze()

# now resolve volume that has not been tracked with features
# bounding box volume minus part volume to get total required volume removal
# untracked volume difference between required and tracked
bbox_vol = part.size_x * part.size_y * part.size_z
required_total_volume_removal = bbox_vol - part.volume
untracked_volume = required_total_volume_removal - tracked_volume
# make a dynamic variable for untracked volume percentage so
# you can have it as a reference at quote_time
untracked_vol_percentage = var('Untracked Vol %', 0, 'Percentage of volume not tracked with feature iteration', number, frozen=False)
untracked_vol_percentage.update(round(untracked_volume / required_total_volume_removal * 100, 2))
untracked_vol_percentage.freeze()

# now apply a leftover volume removal rate on untracked volume based on material family
# in inches/minute
leftover_volume_removal_rate = {
  'Aluminum': 5,
  'Stainless Steel': 2,
  'Steel': 3,
}
if part.material_family in leftover_volume_removal_rate:
  leftover_rate = leftover_volume_removal_rate[part.material_family]
else:
  leftover_rate = leftover_volume_removal_rate['Stainless Steel']

untracked_runtime = var('Untracked RT', 0, 'Runtime of untracked volume removal', number, frozen=False)
untracked_runtime.update(round(untracked_volume / leftover_rate, 3))
untracked_runtime.freeze()

# define total runtime and setup_time variables for operation overriding
runtime = var('runtime', 0, 'Runtime in hours', number, frozen=False)
runtime.update((pocket_runtime + hole_runtime + untracked_runtime) / 60)
runtime.freeze()

# just a basic 30 minute setup time, does not need to be dynamic because its just a constant
setup_time = var('setup_time', 0.5, 'Setup time in hours', number)

# define setup and machine rates to come up with a price
setup_rate = var('Setup rate', 80, '$/hr', currency)
machine_rate = var('Machine rate', 35, '$/hr', currency)

PRICE = setup_rate * setup_time + runtime * part.qty * machine_rate
DAYS = 0
```
