---
title: "CAD assembly file processing"
slug: CAD-assembly-file-processing
source: https://help.paperlessparts.com/s/article/CAD-assembly-file-processing
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# CAD assembly file processing

> Source: https://help.paperlessparts.com/s/article/CAD-assembly-file-processing  
> Topic: Part Analysis & Interrogation

When uploading a [supported CAD file format](https://help.paperlessparts.com/s/article/supported-file-types) to Paperless Parts, it enters a 3D file processing pipeline designed to extract as much information as possible from the file while condensing identical geometry to make quoting easier.

This article explains this processing behavior as well as possible issues or failure cases at each step.

---

## **Uploading**

Paperless Parts accepts CAD assembly files up to 250mb in size through drag-and-drop or click-to-upload actions or Open API upload endpoints to the part library, quote sidebar, quote item child components and quote supporting files.
Uploading requires a stable internet connection, and may take longer for larger files up to 250mb. If uploading fails, no further processing can occur.
*Uploading may fail if your internet connection is interrupted.*

## **Virus scanning**

After uploading succeeds, Paperless Parts will perform a virus scan of the file to protect you from malware. If Paperless Parts detects malware within your file, no further processing will occur and you will be prevented from downloading the file as well as prompted to delete it from the system. However, if the file was uploaded to the part library, quote sidebar, or assembly components tables, parts and/or line items will still be created.

![](/servlet/rtaImage?eid=ka0Ns00000034gb&feoid=00N5G00000WB8Hk&refid=0EMNs000008FCkD)

## **Bill Of Materials (BOM) breakout**

Once an assembly file is uploaded and is determined not to contain a virus, Paperless Parts will attempt to break out its assembly BOM by matching the structure found within the file. Assembly nodes will be created for groups of bodies, while standalone geometry will be body nodes. Paperless Parts will also attempt to combine connected individual faces into single bodies where possible.

This step occurs early, in hopes of guaranteeing you receive a BOM for quoting even if geometric processing fails for the geometry of the resulting components.

From this breakout, Paperless Parts will create an individual model file for each non-assembly file and process them independently.

*BOM breakout will fail entirely if the total number of unique components in the file exceeds 1000, and may produce imperfect results when poorly-designed CAD files include non-solid bodies with missing faces.*

![](/servlet/rtaImage?eid=ka0Ns00000034gb&feoid=00N5G00000WB8Hk&refid=0EMNs000008FCkE)

## **Generating thumbnails, viewing data, and geometric search information for each file**

After creating individual files for each non-assembly body in the file, Paperless Parts will generate image thumbnails for parts, 3D data so the part can be viewed in the part viewer, and geometric indexes (used for similar parts matching) for each file.

If any of these generation steps fail, the entire body will fail to process, meaning the part will still appear in the BOM but be without a thumbnail. It will also not be able to be viewed in 3D, interrogated, or identified with matching part search.

This individual processing is designed to maximize the amount of information you receive from complex assembly files, so that a single low-level failure does not break processing of the entire file.

*Subfile processing can fail when the source file contains broken or missing information for that node.*

![](/servlet/rtaImage?eid=ka0Ns00000034gb&feoid=00N5G00000WB8Hk&refid=0EMNs000008FDDF)

## **Squashing identical geometry**

After each file processes, Paperless Parts will apply these results back to the generated BOM, then begin condensing identical geometry into the same part to ensure you can quote each unique part in the assembly at most once.

Paperless Parts identifies identical geometry in two ways: **through pointers in the source file,** which exist when the model author copy-pasted the same body as a part of their design (i.e. many instances of the same hardware), as well as **by looking for identical geometric indices**(bounding box size, center of mass, radius of gyration, length, area, and volume). This approximation of geometric similarity is a strong indicator that two parts are alike, despite varying in orientation or placement.

Paperless Parts will also combine sub-assemblies that share all the same sets of components into the same part, saving you time by reducing the number of subassemblies to quote.

*Squashing identical geometry**very rarely** may fail to combine a part or may squash a very similar, but not identical geometry when the geometric indices are identical, despite variations in the actual geometry; and is more likely to do so in larger files with very similar but non-identical parts.*

## **Ignoring bodies**

Finally, Paperless Parts ignores specific CAD bodies that are either improperly defined by the file author (to be remedied in conversation with the customer in an external CAD system) or unlikely to represent a part (such as reference geometry).

Ignored bodies do not appear within the BOM, but can instead be found within the "CAD" tab in the viewer (along with their name, parent name, and reason they were ignored). The part thumbnail in quotes will also indicate as many errors as ignored bodies.

Specifically, the following conditions will cause a body to be ignored:

- Volume less than 1^-6 mm3
- Bounding box dimension smaller than 1^-6 mm
- Volume / Bounding Box Volume less than 1^-6 mm3
- Volume greater than Bounding Box Volume
- Bounding box dimension larger than 1^10 mm
- No faces or edges
