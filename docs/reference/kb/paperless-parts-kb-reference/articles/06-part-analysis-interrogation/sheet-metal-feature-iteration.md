---
title: "Sheet metal feature iteration"
slug: sheet-metal-feature-iteration
source: https://help.paperlessparts.com/s/article/sheet-metal-feature-iteration
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Sheet metal feature iteration

> Source: https://help.paperlessparts.com/s/article/sheet-metal-feature-iteration  
> Topic: Part Analysis & Interrogation

Sheet metal shops are a fantastic fit for our platform because of the formulaic nature of sheet metal costing. We provide values like cut length, punch hit count, hole setups, thickness, etc. that allow for effective formulaic high level pricing. Now with feature iteration, you can use the information stored within each bend, feature, and manufacturability feedback instance to calculate runtimes, prices, part complexity, etc.

In this article, we will break down each feature and feedback type extracted from our sheet metal interrogation, as well as provide examples of how to use them in your pricing formulas. The cheat sheet below contains all the high level information you will need to get started. For more specifics on what each feature and feedback instance represents, check out our [sheet metal interrogation article](https://help.paperlessparts.com/article/53-sheet-metal-interrogation).

### Cheat Sheet

```
sheet_metal = analyze_sheet_metal()  # request interrogation

for bend in get_features(sheet_metal, name='bend'):  # iterate thru bends
  # the below four lines demonstrate how to access bend information
  bend.properties.angle
  bend.properties.radius
  bend.properties.length
  bend.properties.k_factor
  bend.properties.flange_length # will be 0 if the bend is not connected to a flange
  if is_close(bend.properties.angle, 90):  # check bend angle using is_close helper
    do_something = 1
  else:
    do_something_else = 1

# iterate through other forming features
for offset in get_features(sheet_metal, name='offset'):
  # has same properties as bend, but also offset height
  offset.properties.offset_height
  do_something_with_offsets = 1

for open_hem in get_features(sheet_metal, name='open_hem'):
  do_something_with_hems = 1

for feature in get_features(sheet_metal):  # iterate thru features
  feature.name
  feature.properties
  if feature.name == 'countersink':
    # access information with dot notation into properties
    feature.properties.depth
    feature.properties.major_diameter
    do_something_with_countersink = 1

for feedback in get_feedback(sheet_metal):  # iterate thru feedback
  feedback.name
  feedback.level
  feedback.properties
  if feedback.name == 'cut_near_bend':
    # access information with dot notation into properties
    feedback.properties.dist
    feedback.properties.distance_ratio
    do_something_with_cut_near_bend = 1

# get count of feature type by using len() and specifying name
num_countersinks = len(get_features(sheet_metal, name='countersink'))

# get count of feedback type by using len() and specifying name
num_cut_near_bend = len(get_feedback(sheet_metal, name='cut_near_bend'))

# interact with features and feedback directly from dot operator, returning copies of p3l list objects
# can manipulate these with p3l list functions and methods
features = sheet_metal.features.filter(lambda x: x.name == 'bend').filter(lambda x: x.properties.length > 10).sort(lambda x: x.properties.length)
for bend in iterate(features):
  do_something = 1

for feedback in iterate(sheet_metal.feedback):
  do_something = 1
```

##### Feature Reference

| **Name** | **Properties** |
| --- | --- |
| bend | area, angle, length, k_factor, radius, flange_length |
| bend_relief | area, width, length |
| curl | area, angle, length, k_factor, radius |
| counterbore | area, depth, diameter, volume |
| countersink | area, depth, major_diameter, minor_diameter, semi_angle, volume |
| cutout_feature | area, cut_length, requires_piercing   **Note**: We currently do not count the external cut as requiring a pierce. |
| drilled_hole | area, depth, diameter, volume |
| embossment | depth |
| etching | edge_length |
| offset | area, angle, length, offset_height, k_factor, radius, flange_length |
| open_hem | area, angle, length, k_factor, radius, flange_length |
| punch_multi_hit_feature | area, cut_length |
| circular_punch | cut_length, radius |
| obround_punch | cut_length, side_length, side_width, radius |
| rectangular_punch | cut_length, side_length, side_width |
| slot_punch | cut_length, side_length, radius |
| square_punch | cut_length, side_length |
| tear_drop | area, angle, length, k_factor, radius, flange_length |

##### Feedback Reference

| **Name** | **Level** | **Properties** (short description) |
| --- | --- | --- |
| captive_part | complete_exclusion | n/a |
| close_bends | manufacturing_issue | orientation, bend_separation_to_thickness |
| close_countersink_bores | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| close_cutouts | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| countersink_bore_to_edge | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| curl_near_bend | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| cut_near_bend | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| cutout_to_edge | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| different_bend_directions | cost_driver | n/a |
| exceeds_press_length | complete_exclusion | n/a |
| hem_near_bend | manufacturing_issue | dist, distance_ratio (traversal/thickness) |
| large_bend_radius | manufacturing_issue | ratio (radius/thickness) |
| machining_required | manufacturing_issue | n/a |
| neg_bend_allowance | complete_exclusion | radius, thickness |
| no_bend_relief | manufacturing_issue | n/a |
| no_corner_relief | manufacturing_issue | n/a |
| non_standard_bend_angle | cost_driver | angle |
| shallow_bend_relief | manufacturing_issue | ratio ((depth-radius)/thickness) |
| sheet_metal_large_part | complete_exclusion | length, width, height, max_length, max_width, max_height |
| short_bend | manufacturing_issue | ratio (length/radius) |
| short_flange | manufacturing_issue | length_to_thickness |
| short_hem_return | manufacturing_issue | ratio (distance/thickness) |
| small_bend_radius | manufacturing_issue | ratio (radius/thickness) |
| small_cut | manufacturing_issue | dist (size of cut) |
| small_radius | manufacturing_issue | radius |
| split_bend | cost_driver | stroke_length |
| tight_corner | manufacturing_issue | angle |
| tight_curl | manufacturing_issue | ratio (radius/thickness) |
| tight_hem | manufacturing_issue | ratio (diameter/thickness |
| thin_bend_relief | manufacturing_issue | ratio (width/thickness) |
| unfolded_sheet_metal_large_part | complete_exclusion | length, width, max_length, max_width |
| unfolding_issue | complete_exclusion | n/a |
| w_bend_warning | manufacturing_issue | length, bend_separation |

### Examples

#### Basic

Below describes a way to add price for the appearance of certain types of features and feedback on a part. This operation could serve as a supplement to your standard marking and forming operations to encapsulate added costs for specific features. Checkout our [custom interrogations article](https://help.paperlessparts.com/article/102-custom-interrogations) to find out how to customize your manufacturability feedback outputs.

```
units_in()

sheet_metal = analyze_sheet_metal()

close_cutout_cost = var('Close cutout cost', 0.25, '$ per close cutout found', currency)
cut_near_bend_cost = var('Cut near bend cost', 2.50, '$ per cut near bend found', currency)
curl_cost = var('Curl Cost', 5.0, '$ per curl found', currency)
hem_cost = var('Hem Cost', 5.0, '$ per hem found', currency)

total_close_cutout_cost = len(get_feedback(sheet_metal, name='close_cutouts')) * close_cutout_cost
total_cut_near_bend_cost = len(get_feedback(sheet_metal, name='cut_near_bend')) * cut_near_bend_cost
total_curl_cost = len(get_features(sheet_metal, name='curl')) * curl_cost
hem_count = len(get_features(sheet_metal, name='open_hem')) + len(get_features(sheet_metal, name='tear_drop'))
total_hem_cost = hem_count * hem_cost

PRICE = (total_close_cutout_cost + total_cut_near_bend_cost + total_curl_cost + total_hem_cost) * part.qty
DAYS = 0
```

####

#### Advanced

Below describes an advanced method to cost out a forming operation based on the characteristics of bends in the part. The operation below will start each bend with a base setup time and runtime, and will then increment these times based on added geometric complexity, such as non-90 degree angle bends, long bends, or large radius bends. This uses a lot of list operations. Check out the article on [P3L Lists](https://help.paperlessparts.com/article/215-p3l-lists) for more info.

```
units_in()
sheet_metal = analyze_sheet_metal()

setup_time = var('setup_time', 0, 'Setup time in hours', number, frozen=False)
runtime = var('runtime', 0, 'Runtime in hours', number, frozen=False)

# establish base setup time and time increments in minutes
base_bend_setup_time = 5
st_increment = 2.5

# establish base runtime and time increments in seconds
base_bend_runtime = 30
rt_increment = 10

# establish geometric thresholds for incrementing times
# in inches
medium_radius_thresh = 2.0
large_radius_thresh = 4.0
medium_length_thresh = 20.0
large_length_thresh = 40.0

# establish our variables that we will use as pricing levers in the operation
# also establish their local tracking variables
base_bends = sheet_metal.features.filter(lambda x: x.name == 'bend')

base_bend_count = var('Bend Count', 0, 'Number of bends detected', number, frozen=False)
base_bend_count.update(len(base_bends))
base_bend_count.freeze()

non_ninety_bends = var('Non-90 Bend Count', 0, 'Number of non-90 degree bends', number, frozen=False)
non_ninety_bends.update(len(
  base_bends.copy().filter(lambda x: not is_close(x.properties.angle, 90))
))
non_ninety_bends.freeze()

med_rads = var('Medium Rads', 0, 'Number of bends with medium rads', number, frozen=False)
med_rads.update(len(
  base_bends.copy().filter(
      lambda x: medium_radius_thresh <= x.properties.radius < large_radius_thresh
                or is_close(x.properties.radius, medium_radius_thresh)
  )
))
med_rads.freeze()

large_rads = var('Large Rads', 0, 'Number of bends with large rads', number, frozen=False)
large_rads.update(len(
  base_bends.copy().filter(
      lambda x: x.properties.radius >= large_radius_thresh
                or is_close(x.properties.radius, large_radius_thresh)
  )
))
large_rads.freeze()

med_lengths = var('Medium Lengths', 0, 'Number of bends with medium length', number, frozen=False)
med_lengths.update(len(
  base_bends.copy().filter(
      lambda x: medium_length_thresh <= x.properties.length < large_length_thresh
                or is_close(x.properties.length, medium_length_thresh))
))
med_lengths.freeze()

large_lengths = var('Large Lengths', 0, 'Number of bends with large length', number, frozen=False)
large_lengths.update(len(
  base_bends.copy().filter(
      lambda x: x.properties.length >= large_length_thresh
                or is_close(x.properties.length, large_length_thresh))
))
large_lengths.freeze()

# now collect contributions
total_bend_setup = base_bend_setup_time * base_bend_setup_time
total_bend_run = base_bend_count * base_bend_runtime

total_bend_setup += non_ninety_bends * st_increment
total_bend_run += non_ninety_bends * rt_increment

total_bend_setup += med_rads * st_increment
total_bend_run += med_rads * rt_increment

total_bend_setup += large_rads * 2 * st_increment
total_bend_run += large_rads * 2 * rt_increment

total_bend_setup += med_lengths * st_increment
total_bend_run += med_lengths * rt_increment

total_bend_setup += large_lengths * 2 * st_increment
total_bend_run += large_lengths * 2 * rt_increment

# establish final times as a sum of all above
# convert times to hours
setup_time.update(total_bend_setup / 60)
setup_time.freeze()
runtime.update(total_bend_run / 3600)
runtime.freeze()

setup_labor_rate = var('Setup Labor Rate', 50, 'Labor cost per hour to set up work center', currency)
run_labor_rate = var('Run Labor Rate', 25, 'Labor cost per hour to attend work center machine', currency)

setup_cost = setup_time * setup_labor_rate
run_cost = runtime * run_labor_rate * part.qty

PRICE = setup_cost + run_cost
DAYS = 0
```

####

####
