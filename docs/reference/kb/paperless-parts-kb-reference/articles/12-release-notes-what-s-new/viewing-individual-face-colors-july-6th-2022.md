---
title: "Viewing individual face colors - July 6th, 2022"
slug: viewing-individual-face-colors-july-6th-2022
source: https://help.paperlessparts.com/s/article/viewing-individual-face-colors-july-6th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Viewing individual face colors - July 6th, 2022

> Source: https://help.paperlessparts.com/s/article/viewing-individual-face-colors-july-6th-2022  
> Topic: Release Notes (What's New)

## What's new in v24.20.0

You will be able to view the colors of individual faces as they were designed in the model.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62bf0da30b51ec1ae83fc66e/file-ORfeMadlUg.gif)This functionality is supported for the following file formats:

- Neutral - .STP/.STEP, .JT
- Solidworks - .SLDPRT, .SLDASM (Pack & Go)
- Catia - .CATPart, .CATProduct (Pack & Go)
- Siemens NX - .PRT, .ASM (Pack & Go)
- PTC Creo - .PRT, .ASM (Pack & Go)
- Parasolid - .X_T, .X_B
- Inventor - .IPT, .IAM (Pack & Go)

You can toggle off the face colors using the gear icon in the top right of the viewer:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62bf0dc1c74a080359c85e0a/file-MgWgw4CaRI.gif)

##### ![]()

### Where might this come in handy?

While faces are not often individually colored in models, when they are, it usually indicates aspects of design intent or manufacturing requirements that can be very helpful for estimating. For example, individual faces can be colored to indicate surfaces that must be masked when applying a finish or powder coat. Another example is indicating which faces will be cut with a specific operation, such as calling out features cut with a wire EDM vs a CNC mill.

Let's expand on the finishing example to illustrate the feature's usefulness. Occasionally, only certain surfaces of a part need to have the functional or cosmetic benefits of a finish while other surfaces do not need or must not have the finish. Certain surfaces may be exposed to the elements while others come into contact with other metal surfaces, electronics, human operators, etc. In these situations, the part will require masking. Let's take the part below as an example:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62bf0e390b51ec1ae83fc672/file-gETswjAVaT.gif)

Let's say this part needs to get anodized and then powder coated, but only on certain surfaces. The designer may use the colors on the model to indicate which surfaces will be finished. Above, the gray faces represent areas that will be both anodized and powder coated. Blue represents areas that should just be anodized. Red represents areas that should not be anodized nor powder coated.

Alongside any masking requirements, the primary driver of cost for finishing operations like powder coat and anodizing is surface area. In the partviewer, we can use the selection tool to select the faces of a certain color to see the cumulative area in bottom right. We can then take these surface area values and plug those values into pricing formulas in an operation.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62bf0e8a03382e4311cf0952/file-58KBIgwb8K.png)
