---
title: "Tube laser feature iteration"
slug: tube-laser-feature-iteration
source: https://help.paperlessparts.com/s/article/tube-laser-feature-iteration
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Tube laser feature iteration

> Source: https://help.paperlessparts.com/s/article/tube-laser-feature-iteration  
> Topic: Part Analysis & Interrogation

In this article, we will break down each feature and feedback type extracted from our tube laser interrogation, as well as provide some examples of how to use them in your pricing formulas. The cheat sheet below contains all the high level information you will need to get started. For more specifics on what each feature and feedback instance represents, check out our tube laser interrogation article.

### Cheat Sheet

```
tube_laser = analyze_tube_laser()  # request interrogation

# iterate through cutout features
total_cut_length = 0
total_pierce_count = 0
for cutout_feature in get_features(tube_laser, name='tube_cutout_feature'):
  total_cut_length += cutout_feature.properties.cut_length
  total_pierce_count += 1

total_weld_length = 0
for cutout_end in get_features(tube_laser, name='tube_cutout_end'):
  # tube cutout ends have same properties as regular cutout features
  # but they represent the two ends of the tube
  total_cut_length += cutout_end.properties.cut_length
  total_weld_length += cutout_end.properties.cut_length
  total_pierce_count += 1

for lasered_countersink in get_features(tube_laser, name='lasered_countersink'):
  total_cut_length += lasered_countersink.properties.cut_length
  total_pierce_count += 1
  do_something_with_lasered_countersinks = 1

for feature in get_features(tube_laser):  # iterate thru all features
  feature.name
  feature.properties
  if feature.name == 'lasered_countersink':
    # access information with dot notation into properties
    feature.properties.depth
    feature.properties.major_diameter
    do_something_with_lasered_countersink = 1

for feedback in get_feedback(tube_laser):  # iterate thru feedback
  feedback.name
  feedback.level
  feedback.properties
  if feedback.name == 'angled_cut':
    # access information with dot notation into properties
    feedback.properties.angle
    feedback.properties.cut_length
    do_something_with_angled_cuts = 1

# get count of feature type by using len() and specifying name
num_lasered_countersinks = len(get_features(tube_laser, name='lasered_countersink'))

# get count of feedback type by using len() and specifying name
num_angled_cuts = len(get_feedback(tube_laser, name='angled_cut'))

# access features and feedback directly though dot operator from analyze_ object
# returns copies of p3l lists that can be filtered and sorted
features = tube_laser.features.filter(lambda x: x.name in create_list('tube_cutout_feature', 'tube_cutout_end')).sort(lambda x: -x.cut_length)
for f in iterate(features):
  do_something = 1

for f in iterate(sheet_metal.feedback):
  do_something = 1
```

| **Name** | **Properties** |
| --- | --- |
| tube_cutout_feature | area, cut_length |
| tube_cutout_end | area, cut_length |
| lasered_countersink | area, cut_length, depth, major_diameter, semi_angle |
| counterbore | depth, diameter |
| countersink | depth, major_diameter, semi_angle |

##### Feedback Reference

| **Name** | **Level** | **Properties** (short description) |
| --- | --- | --- |
| angled_cut | manufacturing_issue | cut_length, angle |
| close_countersink_bores | manufacturing_issue | distance, distance_ratio (traversal/thickness) |
| close_cutouts | manufacturing_issue | distance, distance_ratio (traversal/thickness) |
| countersink_bore_to_edge | manufacturing_issue | distance, distance_ratio (traversal/thickness) |
| cutout_to_edge | manufacturing_issue | distance, distance_ratio (traversal/thickness) |
| cylindrical_close_countersinks | manufacturing_issue | distance, distance_ratio (traversal/thickness) |
| cylindrical_close_cutouts | manufacturing_issue | distance, distance_ratio (traversal/thickness) |
| incompatible_tube | complete_exclusion | n/a |
| machining_required | manufacturing_issue | n/a |
