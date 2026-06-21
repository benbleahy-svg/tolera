---
title: "Lathe feature iteration"
slug: lathe-feature-iteration
source: https://help.paperlessparts.com/s/article/lathe-feature-iteration
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Lathe feature iteration

> Source: https://help.paperlessparts.com/s/article/lathe-feature-iteration  
> Topic: Part Analysis & Interrogation

Feature and feedback iteration for lathe processes is useful for calculating things like part complexity from within P3L. The way our lathe interrogation works is it analyzes a part based on your live tooling parameters. You can specify your live tooling parameters in your custom interrogations tab (check our our [custom interrogations article](https://help.paperlessparts.com/article/102-custom-interrogations) for more information). Based on the inputs you give us, it will shape the features and feedback that come out of interrogation. The cheat sheet below will give you all you need to get started. For more specific descriptions on what each of the features and feedback types are, check out our [lathe interrogation article](https://help.paperlessparts.com/article/63-lathe-interrogation).

### Cheat Sheet

```
lathe = analyze_lathe()  # request interrogation

# get features
for feature in get_features(lathe):
  feature.name
  feature.properties
  do_something = 1

# get feedback
for feedback in get_feedback(lathe):
  feedback.name
  feedback.level  # cost_driver, manufacturing_issue, complete_exclusion
  feedback.properties
  do_something = 1

# get features by specific name
for hole in get_features(lathe, name='live_tooling_hole'):
  hole.properties.depth
  hole.properties.volume
  do_something = 1

# get feedback by specific name
for cavity in get_feedback(lathe, name='asymmetric_cavity'):
  do_something = 1

# get count of feature type
count_of_holes = len(get_features(lathe, name='live_tooling_hole'))
# get count of feedback type
count_of_off_axis_holes = len(get_feedback(lathe, name='off_axis_hole'))

# access features and feedback directly using the dot operator from the analyze_lathe object
# returns copies of p3l lists that can be manipulated
features = lathe.features.filter(lambda x: x.name == 'live_tooling_hole').sort(lambda x: -x.area)
for f in iterate(features):
  do_something = 1

for f in iterate(lathe.feedback):
  do_something = 1
```

### Feature Reference

| **Name** | **Properties** |
| --- | --- |
| lathe_internal_cut | area |
| lathe_external_cut | area |
| lathe_setup | n/a |
| live_tooling_axial_direction | area |
| live_tooling_cavity | area |
| live_tooling_hole | area, bottom_type (flat, obstructed, tipped, thru), depth, min_radius, volume |
| live_tooling_protrusion | area |
| live_tooling_radial_direction | area |

### Feedback Reference

| **Name** | **Level** | **Properties** |
| --- | --- | --- |
| asymmetric_cavity | cost_driver | n/a |
| bore_hole_wo_relief | cost-driver | relief_depth_to_diameter |
| lateral_tool_space | manufacturing_issue | n/a |
| lathe_incompatible_faces | manufacturing_issues | n/a |
| lathe_long_part | complete_exclusion | n/a |
| lathe_slender_part | cost_driver | length_to_min_diameter |
| lathe_small_internal_rad | cost_driver | radius |
| lathe_steep_profile | cost_driver | angle |
| lathe_uncuttable_faces | manufacturing_issue | n/a |
| lathe_wide_part | complete_exclusion | n/a |
| no_lathe_axis | complete_exclusion | n/a |
| off_axis_hole | manufacturing_issue | area, bottom_type (flat, obstructed, tipped, thru), depth, min_radius, volume |

### Example

The example below demonstrates how to come up with a basic complexity metric of the part based on the appearance of certain features and feedback.

```
units_in()
lathe = analyze_lathe()

# level 1, 2, or 3
complexity = var('Complexity', 0, 'Part complexity', number, frozen=False)

# if there are either asymmetric cavities or off axis holes, immediately level 2
# if there are more than 10, level 3
count_cavity = len(get_feedback(lathe, name='asymmetric_cavity'))
count_holes = len(get_feedback(lathe, name='off_axis_hole'))
total_count = count_cavity + count_holes
if 0 < total_count <= 10:
  complexity.update(2)
elif total_count > 10:
  complexity.update(3)

# if the part is either too long or to wide, immediate level 3
is_wide = len(get_feedback(lathe, name='lathe_wide_part')) > 0
is_long = len(get_feedback(lathe, name='lathe_long_part')) > 0
if is_long or is_wide:
  complexity.update(3)

complexity.freeze()
# store complexity in workpiece for utilization in downstream ops
set_workpiece_value('complexity', complexity)

PRICE = 0
DAYS = 0
```
