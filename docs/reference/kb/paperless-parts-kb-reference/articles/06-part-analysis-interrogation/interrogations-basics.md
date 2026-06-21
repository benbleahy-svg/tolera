---
title: "Interrogations"
slug: interrogations-basics
source: https://help.paperlessparts.com/s/article/interrogations-basics
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Interrogations

> Source: https://help.paperlessparts.com/s/article/interrogations-basics  
> Topic: Part Analysis & Interrogation

**Interrogations**are algorithms corresponding to manufacturing processes that Paperless Parts runs on 3D models. They identify key part dimensions, manufacturing features, and potential manufacturability issues.

Paperless Parts offers seven different process interrogations:

- [Sheet Metal](https://help.paperlessparts.com/s/article/sheet-metal-interrogation)
- [Tube Laser](https://help.paperlessparts.com/s/article/tube-laser-interrogation)
- [CNC Milling](https://help.paperlessparts.com/s/article/milling-interrogation)
- [CNC Lathe/Turning](https://help.paperlessparts.com/s/article/lathe-interrogation)
- Cast Urethane
- Additive
- Wire EDM

---

# What files and parts be interrogated?

Paperless Parts can interrogate single CAD bodies from [supported file types](https://help.paperlessparts.com/s/article/supported-file-types)that fall under the interrogation file size limits.

This means that **only non-assembly parts can be interrogated,**because they contain single CAD bodies. Assembly parts cannot be interrogated because they reference multiple CAD bodies.

### Interrogation file size limits

Paperless Parts will interrogate 3D files up to a certain file size, depending on the file type. For single-body CAD files, this will be the size of the original file; and for bodies within assemblies, this will be the file size of the single body that Paperless Parts creates internally when it unpacks the BOM of the file.

| **Interrogation(s)** | **Limit** |
| --- | --- |
| Cast Urethane, CNC Milling, CNC Lathe/Turning, Wire EDM | Up to 20mb |
| Sheet Metal, Tube Laser | Up to 50mb |
| Additive | None |

---

# How can I run interrogations?

## From the part viewer

Within the Part Viewer, you can both run interrogations as well as view their results. To do so, select a non-assembly part within the BOM tab, then click on the CAD tab and navigate to the “Geometric Features” branch.

From there, select a process, optionally select the part’s material, select a specific interrogation, then click “interrogate file”.

**Interrogations run from the viewer do not automatically apply to costing in an active quote; to apply interrogations to costing, see below.**

## From quotes (automatically, via P3L)

Depending on your account configuration, Paperless Parts may run specific interrogations when adding certain material or labor operations or a custom process to a quote. For example, adding a sheet laser operation that contains analyze_sheet_metal() in its P3L formula will automatically run a sheet metal interrogation.

This ensures that you can focus on building your router, and let Paperless Parts' analysis run *for you*in the background.

You can always view these interrogation results within the part viewer; and depending on your account configuration, you may be able to view some interrogation results within those operations.

**Interrogations run by your operations apply their results to your part costing.**

---

# Can my shop customize interrogation results / parameters?

Your shop has the ability to customize the parameters used for your interrogation’s warnings via [custom interrogations](https://help.paperlessparts.com/s/article/custom-interrogations), allowing you to cater interrogation behavior to your shop’s manufacturing ability.
