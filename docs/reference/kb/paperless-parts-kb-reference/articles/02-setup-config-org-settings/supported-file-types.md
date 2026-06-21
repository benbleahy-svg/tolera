---
title: "Supported file types"
slug: supported-file-types
source: https://help.paperlessparts.com/s/article/supported-file-types
topic: "Setup, Config & Org Settings"
captured: 2026-06-19
---

# Supported file types

> Source: https://help.paperlessparts.com/s/article/supported-file-types  
> Topic: Setup, Config & Org Settings

The following file types are supported in Paperless Parts for viewing and quoting:

Standard Brep:

- STEP (**.step, .stp, .stpz**)
- Jupiter Tessellation (**.jt**)

Converted Brep:

- Autodesk (**.ipt**)
- ACIS (**.sat, .sab**)
- Rhino (**.3dm**)
- CATIA V4 (**.exp, .model**)
 CATIA V5 ( **.catpart, .catshape**)
- Solid Edge (**.par, .psm**)
- Parasolid (**.x_b**, **.x_t**)
- SolidWorks (**.sldprt**)
- Creo (**.neu, .prt**)
- Unigraphics/NX ( **.prt**)
- IFC (**.ifc**)

Vector / Print:

- Standard / AutoCAD (.**dxf**)
- Many / AutoCAD (**.dwg**)
- Scalable Vector Graphics (**.svg**)
- Print (**.pdf, .tif, .tiff,**image files:**.jpeg, .png**)
- Office Files (**.pptx, .xlsx, .ods, .odp**)
- Spreadsheets (**.csv, .ods,****.xlsx**)
- Plain Text (**.txt**)
- Email files (**.msg**, **.eml**)
  - Note: We will also parse the attachments of emails.
- **bib, csv, dbf, dif, doc, docx, emf, eps, epub, fodg, fodp, fods, fodt, html, ltx, met, odd, odp, ods, odt, otg, ots, ott, pbm, pct, pdb, pgm, pot, potm, ppm, pps, ppt, pptx, psw, pwp, pxl, ras, rtf, sda, sdc, sdw, slk, ssd, stc, std, sti, stw, svm, swf, sxc, sxd, sxi, sxw, txt, uop, uos, uot, vor, wmf, wps, xhtml, xls, xlst, xlt, xml, xlsx, xpm**
- **Note.**Currently we support sheet metal interrogation for the following vector file types: **DXF, DWG**, and **vectorized PDF****s**. See our [PDF Vectorization](https://help.paperlessparts.com/s/article/pdf-vectorization) feature to convert PDFs to DXFs.

Mesh:

- Standard Mesh ( **.stl, .3mf**)
- 3D PDF (Adobe)
- Autodesk ( **.3ds, .dwf, .dwfx**)
- CATIA V5 ( **.cgr**)
- CATIA V6 ( **.3dxml** )
- COLLADA (**.dae**)
- GL Transmission Format (**.glb**)
- FBX (**.fbx**)
- Wavefront OBJ (**.obj**)
- PRC (**.prc**)
- VRML (**.vrml, .wrl**)

Pack-and-go:

- ZIP file with:
  - SolidWorks (**.sldprt and .sldasm**)
  - PTC Creo (**.prt****and .asm**)
  - CATVIA (**.catpart and .catproduct**)
  - Autodesk (**.ipt and** **.iam)**
- ***Note -***SLDASM / ASM / Catproduct / IAM files are assembly instruction manuals to SLDPRTs / PRTs / Catparts / IPTs being the actual components and where the geometry is actually stored. *Both are needed* to construct the entire package. Instructions on how to upload-pack and go assemblies are outlined below. Uploading one without the other will produce an unable to display error.

You can upload other file formats but they will not be viewable in the system. Note that you can drag entire folders (including folders that contain nested folders) of files into a quote in Paperless and all of the files will be parsed out of the folders.

The following file types are supported for interrogation:

- **exp, step, stp, sldprt, iges, igs, ifc, catpart, catshape, cgr, 3dm, x_b, x_t, ipt, jt, model, neu, prt, psm, sab, sat, par, stpz.**

Use a format we don't support? Contact [support@paperlessparts.com](mailto:mailto:support@paperlessparts.com) and let us know.

Please note that the geometry of IGS files will be slightly modified (or "healed") before any interrogation is performed. This also applies to any file with non-solid bodies or type Spline faces.These geometry modifications are extremely minor and are equivalent to the changes any CAD file goes through when it is converted to a .STEP file, but we'll still alert you anytime they happen with a "Resolved error" warning. If you download a file with a "Resolved error", you'll download the original, unmodified version of the file.

### For Best Results, Use STEP and Native CAD File Formats

When quoting, upload STEP files or native CAD file formats like SLDPRT from SolidWorks to maximize the geometric analysis done to power your quotes.

Note that we currently do not support files over 150 MB in size. If your file is not appearing correctly, check the size or review our documentation on [Common part errors and troubleshooting](https://help.paperlessparts.com/s/article/common-part-errors-and-troubleshooting).

### Uploading Pack-and-go Assemblies

Paperless Parts supports the upload of pack-and-go assemblies within a ZIP file from SolidWorks, PTC Creo, Catia, and Inventor. Either collect all associated model and assembly files into a folder and compress that folder into a ZIP file (SolidWorks: sldprt and sldasm, PTC Creo: prt and asm, Catia: catpart and catproduct, Inventor: ipt and iam) **or** use built-in pack-and-go functionality:

#### SolidWorks

Go to File > Pack-and-go > Configure with the settings highlighted in red below > Save

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/60ae913f2246b50b7f38f55f/file-0nkcTanf0L.png)

To learn more, check out [Solidworks's Pack and Go documentation](https://help.solidworks.com/2021/english/SolidWorks/sldworks/c_pack_go_ovw_wpdm.htm).

#### Inventor

Go to File > Save As > Pack-and-go > Configure with the settings highlighted in red below > Search Now > Start

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/60ae932bafcffb241935e7b2/file-HdP7RV5s29.png)

To learn more, check out [Autodesk's Pack and Go documentation](https://knowledge.autodesk.com/support/inventor/learn-explore/caas/CloudHelp/cloudhelp/2020/ENU/Inventor-Help/files/GUID-730304AA-13BD-467B-9351-C7C1362876BD-htm.html#:~:text=In%20Autodesk%20Inventor%2C%20click%20File,Assistant%20session%20outside%20Autodesk%20Inventor).

#### PTC Creo and Catia

Similar to the SolidWorks and Inventor steps, pack-and-go should be found either in the File drop-down or in File > Save As options. Ensure you are saving the package as a ZIP file, and make sure to include all components.

To learn more, check out [PTC's documentation on Exporting Assemblies to STEP](http://support.ptc.com/help/creo/creo_pma/usascii/index.html#page/data_exchange%2Finterface%2FExporting_Part_or_Assembly_to_STEP.html%23).

###
