---
title: "Feature iteration"
slug: feature-iteration
source: https://help.paperlessparts.com/s/article/feature-iteration
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Feature iteration

> Source: https://help.paperlessparts.com/s/article/feature-iteration  
> Topic: Part Analysis & Interrogation

Our geometric interrogation performs extensive feature and manufacturability feedback detection on CAD files that are uploaded to the system. You can even create custom interrogations to specify what features and feedback look like for a part based on process and material information. Previously, the only place to access the information associated with these features and manufacturability feedback was in our part viewer. Now, with feature iteration, we give you all of this information from within P3L so you can use it to influence pricing logic.

#### If you want to implement custom feature-based runtime/pricing algorithms, this is where to start.

In this article, we will discuss high level principles and how to access feature and manufacturability feedback information. In related articles, we will break down the specifics for each type of manufacturing process, as well as provide more specific examples. **Combine feature iteration with**[custom interrogations](https://help.paperlessparts.com/s/article/custom-interrogations)**for an even more streamlined workflow and customized experience.**

## Overview

When you request interrogation information within P3L using an `analyze_*()` command (`analyze_mill3()`, `analyze_sheet_metal()`, `analyze_lathe()`, `analyze_wire_edm()`, `analyze_additive()`, or `analyze_casting()`), it returns a blob of information about the part in context with that manufacturing process type. Lets take the output of an `analyze_sheet_metal()` call for example. In this blob of information exists important pricing information like **total_cut_length**, **total_hole_setups**, **thickness**, etc that you can use for straightforward pricing logic. However, when you want to break pricing down into a feature by feature exercise, these basic numbers fall short of providing the information you need. Now with feature iteration, we provide helper functions for you to extract all that in depth information about each feature and manufacturability feedback you can see in our part viewer.

## How to access information

While the way to access this information is slightly different for each process type, you use four basic iterator functions:

`get_setups(analyze_output) -> P3LList`

Given the output of an `analyze_*()` call, this function returns a P3LList of all setups for the part. This method is useful for `analyze_mill3()` and `analyze_wire_edm()` outputs, as with these processes, we store features and feedback within the actual setups they pertain to, as well as storing all features and feedback with the top level `analyze_output` including those that do not pertain to any individual setup.

`get_features(analyze_output_or_setup, name=None) -> P3LList`

Given the output of an `analyze_*()` or a `setup` object from the `get_setups` iterator, this function returns a P3LList of all features within the object. Setups accessed using a CNC-style process with the INDEX value also can be passed as an input to this function. You can optionally specify a **name** that will return a list of only the features with a name that matches the specified value. Just calling `get_features(analyze_output_or_setup)` will return an array of all features.

`get_feedback(analyze_output_or_setup, name=None) -> P3LList`

Given the output of an `analyze_*()` or a `setup` object from the `get_setups` iterator, this function returns a P3LList of all manufacturability feedback found within the object. Setups accessed using a CNC-style process with the INDEX value also can be passed as an input to this function. You can optionally specify a **name** that will return a list of only the feedback with a name that matches the specified value. Just calling `get_feedback(analyze_output_or_setup)` will return an array of all feedback.

## How to use information

Every feature instance that comes out of the `get_features()` function has a **name** and **properties** attribute accessed by dot notation:

```
sheet_metal = analyze_sheet_metal()
for feature in get_features(sheet_metal):
  feature.name
  feature.properties
```

Every feedback instance that comes out of the `get_feedback()` function has a **name**, **level**, and **properties** attribute accessed by dot notation:

```
sheet_metal = analyze_sheet_metal()
for feedback in get_feedback(sheet_metal):
  feedback.name
  feedback.level
  feedback.properties
```

The **level** of a feedback object is a string that can hold one of three values: **cost_driver**, **manufacturing_issue**, or **complete_exclusion**. These are assigned internally by Paperless Parts that dictates the general severity of manufacturability feedback instance, where things like deep holes are cost drivers, tight corners are manufacturing issues, and exceeding size limits are complete exclusions. You can use these levels as a general indicator of how problematic a part is for a certain process. A basic usage for the **level** is seen below using sheet metal:

```
sheet_metal = analyze_sheet_metal()
complexity_metric = 0
for feedback in get_feedback(sheet_metal):
  if feedback.level == 'cost_driver':
    complexity_metric += 1
  elif feedback.level == 'manufacturing_issue':
    complexity_metric += 2
  elif feedback.level == 'complete_exclusion':
    complexity_metric += 3
```

Accessing this information from `get_setups()` works in a very similar manner.

```
mill = analyze_mill3()
for setup in get_setups(mill):
  for feature in get_features(setup):
    feature.name
    feature.properties
  for feedback in get_feedback(setup):
    feedback.name
    feedback.level
    feedback.properties
```

The **properties** from a feature or feedback object has a range of attributes that depend on the type of feature or feedback. All of these properties are accessed via dot notation. For example, features with the name **bend** from a sheet metal output have **area**, **length**, **radius**, **angle**, and **k_factor** attributes are accessed and used like the following snippet:

```
sheet_metal = analyze_sheet_metal()
for bend in get_features(sheet_metal, name='bend'):
  bend.properties.area
  bend.properties.length
  bend.properties.radius
  bend.properties.angle
  bend.properties.k_factor
```

You additionally can use all four iterator functions to quickly check the count of setups, features, feedback, or bends:

```
mill = analyze_mill3()
number_of_setups = len(get_setups(mill))

sheet_metal = analyze_sheet_metal()
number_of_bends = len(get_bends(sheet_metal))

number_of_feedback = len(get_feedback(sheet_metal))
number_of_features = len(get_features(sheet_metal))
```

You also can call the features and feedback arrays directly. These will return a P3LList copy of the feature and feedback objects which you can then manipulate with list methods. Check out our article on P3L Lists for more information on how to use these.

```
sheet_metal = analyze_mill3()
for f in iterate(sheet_metal.features):
  do_something = 1

for f in iterate(sheet_metal.feedback):
  do_something = 1

bends = sheet_metal.features.filter(lambda x: x.name in create_list('bend', 'curl', 'open_hem', 'tear_drop', 'offset')
for b in iterate(bends):
  do_something = 1
```

Checkout our articles on each process to get lists of feature and feedback names as well as their associated properties and levels. These articles also have interesting examples to work from.

- Sheet Metal
- Milling
- Lathe/Turning
- Tube Laser
