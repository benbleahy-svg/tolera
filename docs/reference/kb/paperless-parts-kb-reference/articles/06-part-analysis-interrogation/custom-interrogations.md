---
title: "Custom interrogations"
slug: custom-interrogations
source: https://help.paperlessparts.com/s/article/custom-interrogations
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Custom interrogations

> Source: https://help.paperlessparts.com/s/article/custom-interrogations  
> Topic: Part Analysis & Interrogation

Paperless Parts gives you the ability to customize how certain interrogations geometrically analyze CAD models. For the sheet metal, milling, lathe, and tube laser interrogation modules you can adjust inputs that will affect what features and manufacturability feedback are shown to you in the part viewer. For Paperless Parts Quoting users, custom interrogations can also affect the variables used for generating pricing information.

You can begin creating your own custom interrogations by navigating to the Processes section (for Paperless Part Quoting users) or the Shop Floor section (for Paperless Parts users), found on the left panel.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbaf3062c7d3a7e9ae34e08/file-90un1RlIrv.png)

To create a new custom interrogation, click "New Custom Interrogation", and enter an intuitive name and select a process type in the drop down.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbaf35304286364bc912542/file-5La4udmaUi.png)

Once you have created the new custom interrogation, click it to enter the details page.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbaf6822c7d3a7e9ae34e43/file-7se7616W7N.png)Each custom interrogation has a unique name, process type, set of "task inputs", and a matrix of relationships to material information and/or operation information. These "task inputs" are described here for [sheet metal](https://help.paperlessparts.com/article/53-sheet-metal-interrogation), [milling](https://help.paperlessparts.com/article/57-milling-interrogation), [lathe](https://help.paperlessparts.com/article/63-lathe-interrogation), and [tube laser](https://help.paperlessparts.com/article/212-tube-laser-interrogation). Custom interrogations act as a link between a specific set of interrogation inputs to zero, one, or more MATERIAL CLASSES (e.g. Metal, Polymer, etc.); zero, one, or more MATERIAL FAMILIES (e.g. Aluminum, Steel, Abs, etc.); zero, one, or more MATERIALS (Aluminum 5052-H32, Stainless Steel 17-4 PH, etc.); and for Paperless Parts Quoting users, zero, one or more OPERATION DEFINITIONS (e.g. Milling, Material Prep, etc.).

These custom interrogations are applied on a geometry in two places. The first place is in the part viewer under the geometric features tab, using the Geometric Analysis widget.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbaf6d02c7d3a7e9ae34e4d/file-qfzV6L54Fd.png)

You can query for applicable custom interrogations by selecting a process type, a material, material class, and/or material family. The Paperless Parts default interrogation for the given process will always be available (unless one of your custom interrogations has all the same inputs as the default). You can select any of these interrogations to request feature detection and manufacturability analysis with the associated task inputs the custom interrogation object contains. Let's set up a basic example using two sheet metal custom interrogations, one tailored for a laser machine, the other tailored for a punching machine. We will not specify links to any materials, material families, or material classes so that these two interrogations will be available no matter what the material selection is.

First the "Laser" custom interrogation, leaving all of the task inputs with their default values:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbaf84104286364bc9125d2/file-tBgqDQOYb3.png)

And now the "Punch" custom interrogation, with the following task inputs (values different from default are boxed in red):

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbc3aa204286364bc913214/file-wmujpsaD6o.png)

Now let's upload a sheet metal part, and go back to the part viewer. With our two new custom interrogations, this is what you will see in the Geometric Analysis widget:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb017a04286364bc912752/file-ZXze7soo5z.png)

Let's first request the "Laser" interrogation and observe the feature outputs.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb033f04286364bc912773/file-KCPSHRLgbj.png)

Now lets request the "Punch" interrogation and observe the feature outputs.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbc3b6b2c7d3a7e9ae35b77/file-D8IcMnpmFd.png)

As you can see, the content of the features and manufacturability warnings is different. For the "Punch" interrogation, our close cutouts and cut near bend threshold values were larger, so we would expect to see more of those warnings, and that is in fact exactly what you see from the two above images.

The second place these custom interrogations are applied is within the quote tool for Paperless Parts Quoting users. When creating an operation definition, you can specify in your P3L pricing formula which types of geometric interrogation you would like to request on the part. When creating a quote item in the quoting tool, you specify the process used to manufacture the part and the material the part will be made out of. Based on the operations in your process, the interrogations you request in your P3L formulas within these operations, and the material on the part, the system will automatically select the most applicable custom interrogations to apply to the part geometry.

Let's set up another example using two milling custom interrogations, one for all types of aluminum, the other for all types of stainless steel. Let's assume we already have a CNC style process called "CNC Machining" that references an operation called "Milling" that requests a three axis milling geometric interrogation (for reference on how to set up processes and operations, check out our other articles).

Here is the "Milling Aluminum" custom interrogation with its corresponding inputs:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb06892c7d3a7e9ae35070/file-3lVytlDonn.png)

Here is the "Milling Stainless" custom interrogation with its corresponding inputs:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb06b204286364bc9127ba/file-gulPDKLnTP.png)

As aluminum is a much more forgiving type of material to work with, we can perform much deeper cutting operations. So our deep hole, deep radiused cut, and deep planar cut thresholds are 20x, 6x, and 8x tool diameter respectively. For stainless steel our deep hole, deep radiused cut, and deep planar cut thresholds are 6x, 2x, and 3x tool diameter respectively.

Let's now create a quote item for a part and select the CNC Machining process with Aluminum 6061-T6 for the material. Let's now create another quote item with the same part and select the Three Axis milling process, but now instead lets select Stainless Steel 17-4 PH.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb07e42c7d3a7e9ae35084/file-WhGUPGOeqp.png)

If we open the viewer for the part from the first quote item. We notice we do not have any warnings for deep holes or cuts:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb082e2c7d3a7e9ae35088/file-jP3ooew8xC.png)

When we open the viewer for the part in the second quote item, we see warnings for all three:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5dbb088704286364bc9127d6/file-OZ7T85ahgT.png)

#### More Details

In some cases, it might be useful to create custom interrogations that could have potentially overlapping material references. For example, say you set up a custom interrogation that maps to all types of Carbon Steel. Carbon steel is a decently machinable material family, but some specific materials within the carbon steel family are much more difficult to work with than others. 1050 is much more machinable than its familial counterpart 12L14-CR. The task inputs/thresholds that your shop likes for 1050 might not be strict enough for parts made out of 12L14-CR. So what you can do is make another custom interrogation specifically for Carbon Steel 12L14-CR, that links to just that specific material and not the Carbon Steel family as a whole. So now if you select the material Carbon Steel 12L14-CR for a part in the quoting tool, there are now two custom interrogation objects that could apply to the part. However, the system will always select the MOST APPLICABLE custom interrogation to a part based on its material. So while 12L14-CR is a part of the Carbon Steel family, because there is a custom interrogation that links to that material specifically, the system will select the more specific custom interrogation to apply.

### Be careful with how you link your interrogations to operations and materials!

While custom interrogations can be used to dramatically improve the results of our interrogations for your shop, they also can cause some issues when used improperly. If you link one custom interrogation to an operation in a process and another custom interrogation of the same task type to a different operation in that process, the system will actually dispatch TWO interrogations of the same type. This could result in your wait times doubling before you can interact with your quote items. You should always try to consolidate your custom interrogations linkages to operations (and/or processes) so that the system only needs to perform one interrogation of a given type to satisfy interrogation requirements. In general, the system will act intuitively in collecting and satisfying all of the interrogation requirements for a process. However, in more complicated situations, the decisions the system makes might not feel intuitive. We highly encourage you to consult with our support team if you have any questions setting these up.
