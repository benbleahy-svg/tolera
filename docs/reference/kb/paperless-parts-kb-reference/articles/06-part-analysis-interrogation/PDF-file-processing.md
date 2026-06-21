---
title: "PDF file processing"
slug: PDF-file-processing
source: https://help.paperlessparts.com/s/article/PDF-file-processing
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# PDF file processing

> Source: https://help.paperlessparts.com/s/article/PDF-file-processing  
> Topic: Part Analysis & Interrogation

When .pdf files are uploaded to Paperless Parts, they enter a processing pipeline designed to extract key manufacturability information from print content and any contained files or metadata. This processing enables special behavior for the contents of 3D PDFs and PDFs containing other files.

This article explains this processing behavior as well as possible issues or failure cases at each step.

## Uploading

Paperless Parts accepts CAD assembly files up to 250mb in size through drag-and-drop or click-to-upload actions or Open API upload endpoints to the part library, quote sidebar, quote item child components and quote supporting files.

Uploading requires a stable internet connection, and may take longer for larger files up to 250mb. If uploading fails, no further processing can occur.

*Uploading may fail if your internet connection is interrupted.*

## Virus scanning

After uploading succeeds, Paperless Parts will perform a virus scan of the file to protect you from malware. If Paperless Parts detects malware within your file, no further processing will occur and you will be prevented from downloading the file as well as prompted to delete it from the system. However, if the file was uploaded to the part library, quote sidebar, or assembly components tables, parts and/or line items will still be created.

## Unlocking code-protected files

When PDFs are protected by a password, Paperless Parts will *not*continue processing to unpack and process their contents. Instead, Paperless Parts requires you to unlock the file by entering the password--which [can be done within quote files.](https://help.paperlessparts.com/s/article/New-actions-for-Quote-Supporting-Files-August-31st-2023#code)

After the file is unlocked, it will be re-uploaded, re-scanned for viruses, and then the remaining processing will continue.

## PDFs-as-zips unpacking

Large OEMs sometimes share PDFs that are effectively ZIP files -files that both contain a PDF as well as a number of other files including STEP 242, HTML, and more. Whenever these PDFs are uploaded to Paperless Parts, the system will automatically extract them to the same file location as the primary file--either quote files (when forwarding emails or uploading to quote files) or part files (when parts come in through SmartRFQ or are uploaded to part files).

Notably, this behavior is ***not*****the same as 3D PDF model extraction (described below),**as that extracts a model that was included as metadata, not a dedicated model file.

## 3D PDF model extraction

Large OEMs sometime share 3D PDFs - PDF files that when viewed in adobe acrobat contain an interactive 3D model and may include general PMI, specific PMI, views and an interactive BOM. Whenever these PDFs are uploaded to Paperless Parts, the system will automatically extract an STL 3D model used for rendering (including any associated PMI) to the same file location as the primary file--either quote files (when forwarding emails or uploading to quote files) or part files (when parts come in through SmartRFQ or are uploaded to part files). Opening the original PDF will display its static content, **without** any native 3D interactivity.

Notably, when these 3D pdfs are uploaded directly to the primary file of a part (manually or through the SmartRFQ), the extracted STL will become the primary file, while the PDF will be moved to the supporting file.

Notably, this behavior is ***not*****the same as PDFs-as-zips unpacking (described above),**as that extracts files explicitly packaged within the PDF as specific file types, as opposed to 3D PDF metadata that is more loosely defined.

## Scanned PDF Optical Character Recognition (OCR)

Some PDFs that were printed and scanned or otherwise lost their text layers when traveling between systems are processed by an Optical Character Recognition (OCR) system that attempts to visually identify the text on the page and insert it into the page.

This processing enables text that was handwritten or flattened into pixels to be selected and copied from the file in the viewer.

## Print content analysis

Finally, after all other processing as completed, PDF pages will be scanned by a combination of text searching and Paperless-Parts internal AI for valuable content that feeds **part field suggestions**and **extractions,**which are presented within [part fields in the quote](https://help.paperlessparts.com/s/article/Quote-Setup#Partinfo) and part setup tool as well as the [found-in-files container.](https://help.paperlessparts.com/s/article/Found-in-files-extractions)

See the above feature pages for specific information on what is extracted and where.
