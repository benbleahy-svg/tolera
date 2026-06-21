---
title: "\"Found in files\" extractions"
slug: Found-in-files-extractions
source: https://help.paperlessparts.com/s/article/Found-in-files-extractions
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# "Found in files" extractions

> Source: https://help.paperlessparts.com/s/article/Found-in-files-extractions  
> Topic: Part Analysis & Interrogation

Paperless Parts Wingman AI extracts a wide variety of GD&T callouts and requirements from prints (and limited CAD metadata). These are called “extractions”; include control frames, countersinks, counterbores, dimensions & tolerances, surface finish, and more; and are presented in a single, organized panel in the quote and quote part viewer.

Together, this feature:

- Helps novice team members better understand drawings
- Ensures all estimators not miss a critical requirement
- Ensures your whole team approaches requirements consistently process when coupled with custom rules in [Requirements Review](https://help.paperlessparts.com/s/article/requirements-review)

Read on for everything you need to know.

---

## What does Wingman work on, and when does it look?

Wingman will analyze the first 10 pages of .pdf and .tiff file prints when files are uploaded and moved to line item or component primary or supporting files.

Wingman’s detection process occurs in two phases:

- **Quote setup pass (entire file):**When a file is first uploaded to quote supporting files, line item supporting files, or component supporting files, Wingman will look for key quote setup information including part number, revision, description, material, and BOM tables.
  - You can tell this has finished because the file has finished uploading.
  - This pass detects the units of the document and sets the file’s default units (in. or mm), which can be changed at the upper right of the pdf viewer.
- **Full requirements pass (per page):**After the file is added within a line item, Wingman will look for as many GD&T and callout requirements as it knows how to find, including control frames, countersinks, counterbores, holes, threads, surface finish, chamfers, dimensions & tolerances, and much more.
  - You can tell this has started when a purple glow and spinner appears on the “Found in Files” panel in the quote or at the top of the Quote Part Viewer.
  - If units are specified on these callouts, they will include them automatically; if not, units will fall back to the default document units (in. or mm).
  - Tolerances across all callouts detect unilateral, bilateral, and limit tolerances.
  - *Note that this only runs on pages determined to be a “print” during the first pass.*

Wingman currently does **NOT**analyze DXFs/DWGs with GD&T and notes or CAD files with MBD/PMI embedded, which includes 3D PDFs.

![](/servlet/rtaImage?eid=ka0Ns0000009TcH&feoid=00N5G00000WB8Hk&refid=0EMNs00000QkAob)

---

## Where do I view extractions?

To view extractions, make sure a file has finished processing both upload and additional AI processing, described above.

Then, navigate to the “Found in files” panel beneath the component, or in the viewer’s ecosystem app bar. From here, you will see an array of extractions across 5 categories: quote setup, requirements, features, dimensions, and regions.

Found in files groups findings from across files within the same component - meaning if you have an assembly with child components, you’ll need to navigate to those child components to see findings there.

![](/servlet/rtaImage?eid=ka0Ns0000009TcH&feoid=00N5G00000WB8Hk&refid=0EMNs00000QkAv3)

Within each category, text or pills will show individual findings, which can be clicked on to view what was detected and what Paperless Parts has translated it to be; or if in the viewer, additional actions to copy the extracted content including GD&T symbols as well as build a [Requirements Review](https://help.paperlessparts.com/s/article/requirements-review) rule off of the finding. If viewed from the quote, a quick helper link will be present and allow you to jump to the viewer to see the finding in context.

![](/servlet/rtaImage?eid=ka0Ns0000009TcH&feoid=00N5G00000WB8Hk&refid=0EMNs00000QkAtS)

When viewed in the viewer, extractions will be highlighted on prints by default and can be clicked on to view details, even when found in files isn’t open. This default highlighting can be turned off with a checkbox at the upper right of the print.

At this same location, you can change the “units” of the document, which are detected automatically but can be wrong--this will correct the display of all extractions that were unit-less in the source document.

![](/servlet/rtaImage?eid=ka0Ns0000009TcH&feoid=00N5G00000WB8Hk&refid=0EMNs00000QkBBB)

When opening found in files, all extractions will be raised in prominence. However, to get a better view of the print, you can use the “whiteout” toggles to suppress content - making it easier to see specific categories, including finding datums corresponding to control frames.

![](/servlet/rtaImage?eid=ka0Ns0000009TcH&feoid=00N5G00000WB8Hk&refid=0EMNs00000QkBJF)

---

## What can I do with extractions?

Today in Paperless Parts, you can:

- Apply part number, revision, and description suggestions from their detections when clicked in the viewer
- Set X, Y, and Z from dimensions in prints when you don’t have a model
- Copy-paste requirements text into viewer
- Mark them as inaccurate / replace them to help train the system over time
- Build rules to capture critical requirements for your shop with [Requirements Review](https://help.paperlessparts.com/s/article/requirements-review)

At this time, extractions are *not*fed directly into P3L operation generation or costing formulas.

---

## What are all of the extractions Wingman can find?

### Quote setup

| **Extraction** | **Details** |
| --- | --- |
| Part number | Explicit part number text found in prints (often in the title block) or CAD file metadata (under an explicit “part number” keyword). |
| Revision | Explicit revision text found in prints (often in the title block) or CAD file metadata (under an explicit “revision” or “rev” keyword). |
| Description | Explicit description text found in prints, often in the title block under “title” or “part description”. |
| Drawing number | Explicit drawing number text found in prints, often in the title block. |
| Document units | The default units of a print page, often found in the title block. |
| Tables | Tables found in prints or spreadsheets. Missed or incorrect tables can be found/corrected in prints with the “drag to detect” button at the top right of the PDF viewer. |
| BOM tables | BOM tables found in prints or spreadsheets, automatically translated from some tables. Missed or incorrect BOMs can be found/corrected in prints with the “drag to detect” button at the top right of the PDF viewer. |
| Export-controlled | Instances of "CUI", "Export-Controlled", or "ITAR" to determine if the print is likely export-controlled / controlled unclassified information (CUI). |
| PII | Personal identifying information including names, email addresses, phone numbers, physical addresses, and URLs. |

### Requirements

| **Extraction** | **Details** |
| --- | --- |
| Process keywords | Common process keyword segments on the **print**, including: "heat treat", "anodiz", "mask", "chrom", "polish", "ultrasonic", "bead blast", "paint", "stamping", "powder coat", "powdercoat", "anneal", "passivate", "etch", "dye", "weld", "spotweld", "braz","weld", "solder", "forg", "chem film", "gold", "silver", "galvaniz", "conversion coat", "silkscreen", "silk screen", "engrav", "deburr", "spotfac", "peen", "cast", "mold", "sand blast", "broach", "grind", and "degreas" |
| Material | **From prints:**A Paperless Parts global material family or material that likely applies to your part, based on a section of text within the print. **From CAD file metadata:**capitalization-ignored, non-alphanumeric/stripped spaces metadata keys matching the following: “materialname”, “material”, “ptcmastermaterial”, “nxmaterial”, “cadmaterial”, “materialspecification”, “materialdescription”, “longmaterial”, “ptcmaterialname”, “materialtype”, and “swmaterial”. |
| Specifications | A variety of standard and OEM-specific specifications, including: AMS, ASTM, MIL, NADCAP, Airbus, Boeing, Bell, Textron Aviation, GE Aerospace, Gulfstream, Honeywell, Liebherr Aerospace, MTU Aero Engines, Pratt & Whitney, Rolls-Royce, Safran, Northrop Grumman, Lockheed Martin, IAI, Bombardier, Messier-Dowty, Stryker, Medtronic, Hughes / Raytheon legacy |
| Global tolerances | Text inside of the global tolerances block, often found within the title block of a print. |
| Flag notes | Callouts indicating where specific itemized notes are found on the print. |

### Features

| **Extraction** | **Details** |
| --- | --- |
| Hole | Hole callouts on prints, including diameter, depth, tolerances, and threads. |
| Thread | Thread callouts on prints, including class, diameter, handedness, pitch, and depth if present. |
| Countersink | Countersink callouts on prints, including diameter, depth, and angle if present. |
| Counterbore | Counterbore callouts on prints, including diameter and depth if present. |
| Control frame | Control frame callouts of all types, including type, value, datum references, and material condition. Applies to stacked callouts as well as regular callouts. |
| Datum | Datum callouts on prints, denoted by a letter inside of a rectangular box. |
| Chamfer | Chamfer callouts on prints, including length 1, length 2, and angle if present. |
| Surface finish | Surface finish callouts on prints, including class, material removal type, |
| Bend lines | Bend line callouts on prints, including direction, angle, and internal radius. |
| Welds | Weld callouts on prints - **currently no additional properties.** |

### Dimensions & tolerances

| **Extraction** | **Details** |
| --- | --- |
| Length | Length callouts on prints, including their value, tolerance, role (basic, critical to quality, or reference), and indicators like “STOCK” and “TYP”. |
| Diameter | Diameter callouts on prints, including their value, tolerance, role (basic, critical to quality, or reference), and indicators like “STOCK” and “TYP”. |
| Radius | Radius callouts on prints, including their value, tolerance, role (basic, critical to quality, or reference), and indicators like “STOCK” and “TYP”. |
| Angle | Angle callouts on prints, including their value, tolerance, role (basic, critical to quality, or reference), and indicators like “STOCK” and “TYP”. |

### Regions

Some region extractions--notes list, title block, and 2D & 3D views--are hidden by default, but can be spotlighted by clicking them in Found in Files. This ensures you normally have a clean view of your print.

| **Extraction** | **Details** |
| --- | --- |
| Title block | The title block of a page of a print. |
| Notes list | Notes list(s) found on pages of prints. |
| Section view caption | The caption found below a section view in the print. |
| Profile view caption | The caption found below a profile view in the print. |
| 2D view | 2D views, often closely related to section or profile view captions. |
| 3D view | 3D views that often show an isometric view of the part. |

---

# FAQ

### Can you extract [x] from my files in the future?

If you're interested in us presenting extractions for something else within your prints & models, please send feedback to [support@paperlessparts.com](mailto:support@paperlessparts.com)!
