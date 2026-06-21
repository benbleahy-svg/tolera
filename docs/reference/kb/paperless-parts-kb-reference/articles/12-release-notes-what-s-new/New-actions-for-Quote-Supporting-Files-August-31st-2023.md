---
title: "Quote Files and File Processing"
slug: New-actions-for-Quote-Supporting-Files-August-31st-2023
source: https://help.paperlessparts.com/s/article/New-actions-for-Quote-Supporting-Files-August-31st-2023
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Quote Files and File Processing

> Source: https://help.paperlessparts.com/s/article/New-actions-for-Quote-Supporting-Files-August-31st-2023  
> Topic: Release Notes (What's New)

Use the Quote Files area to store and process the files associated with an RFQ. Actions in this area include:

- Categorize Quote Files
  - Structured file download
- Rename and Duplicate Quote Files
- Unzip Quote Files
  - Pack and go support
- Open code-protected Quote Files
- Split PDF Files
- Quickly scan for zero-byte files
- Convert Quote Files to line items
- Access Quote Files from a line item

## Categorize Quote Files

The Quote Files section now has three categories that you can drag files into to organize them:

- RFQ
  - Intended to store any files that came in with the original RFQ from your buyer.
- Vendor Quotes
  - Intended to store communication with your vendors, including emails or PDF quotes.
- Supporting Files
  - Any other file that should be stored at the quote level.

![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038n0D)There are no restrictions on which files you can put in these categories, and the only file we will automatically categorize is the “Original RFQ” email (only for quotes created [with email forwarding](https://help.paperlessparts.com/s/article/Email-forwarding)). Any categorization you perform here will carry over when you download files from the quote (learn more below).

## Structured file download

Many of our shops store their files within a shared drive, typically organized into folders. Download your quote’s files to receive a structured zip file that includes a folder for each Quote File category and each line item, which you can add straight to your shared drive.
![image.png](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038mfF)
![image.png](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038mc1)

## Renaming and Duplicating Files

To rename a file, click the three dots to open the action menu and click **Rename**. Type and press enter to save.
![image.png](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038n3R)
The file's new name will be preserved when it is downloaded from Paperless Parts.
Note that this action is not available for files located on more than one quote, including quotes that have been copied or revised.
To duplicate a Quote File, click the three dots to open the action menu and click **Duplicate**. Performing this action on a zip file will also duplicate its contents.
![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038nBV)

## Unzipping Files

If your buyer sends you zipped files, you can preview and unzip these to access their contents from the Quote files area. Click the file, or select the three dots next to it to open the action menu and select **Unzip**.
From the new window, preview the contents of the compressed file and select Unzip to add the contents of the zip file into the Quote Files field. We’ll preserve a copy of the original zip file, which we suggest storing in another file category (like “RFQ”) if you’re working with a large number of part files.
![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038n0E)
If your zip file contains a pack and go (a common zipped format for assembly files), you do not need to unzip it before converting it to a line item. We’ll flag these types of files to you and keep them bundled by default if you unzip a file that contains them.
![image.png](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038mnJ)
We’ll also flag if the pack and go is missing a file so that you can reach out to your buyer and resolve any missing information before you begin quoting.
![image.png](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs0000038mk5)
 Learn more about pack and go’s [here](https://help.paperlessparts.com/s/article/supported-file-types) .

## Open code-protected Quote Files

If you ever receive code-protected PDFs or .zip files from your buyers, you can open those directly from the Quote Files section before viewing their contents and/or turning them into line items.
Code-protected files will be marked with a "Locked" symbol.
![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs000004pITd)
Either click the file directly or select "Unlock" from the Actions menu to enter the access code.
![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs000004pITe)
After you have entered the correct code and clicked "Unlock", the modal will close. Once the file is done processing, you'll receive a notification that the file is ready and can click the file to unzip it or view its contents.
*Note*: If you download the file out of Paperless at any point, you will receive the **original, locked version**and need to reenter the code to view the file locally.

## Split PDF Files

If a quote file is a PDF with multiple pages, you can create an individual file from each page in the PDF using the "Split" action.

![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs00000E3hEr)

Selecting this action will create an individual quote file from each page of the PDF (named "Original file name (page *N*).pdf") and preserve the original file, adding "(original file)" to the end of its file name.

Note that this action can only be performed on PDFs with <100 pages.

## Zero-byte Files

If a part is unable to load or display in Paperless Parts, one common reason is that it does not have any data associated with it. These are called zero-byte files and sometimes require you to contact your buyer for a new copy. Paperless Parts will now detect if a file is zero bytes and notify you with an icon, as shown below. This way, your team can identify and resolve these issues before opening the file in the viewer. To learn more about troubleshooting zero-byte files, visit this [knowledge base article](https://help.paperlessparts.com/s/article/common-part-errors-and-troubleshooting).
![](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EM5G00000DWoW7)

## Convert Quote Files to Line Items

If one of your Quote Files is a part file that should belong to a line item, you can quickly convert it to a line item by dragging and dropping it into the left nav bar. This action can be performed for single Quote Files or in bulk.

- For a more detailed walkthrough on how to create line items from Quote Files, check out our documentation on Setting up line items .

## Access Quote Files From a Line Item

If you need to quickly access a Quote File while you're working on an item, expand the Quote Files drawer by clicking the arrow on the right side of the screen.
![open QF.gif](/servlet/rtaImage?eid=ka0Ns0000005ADF&feoid=00N5G00000WB8Hk&refid=0EMNs000003AfTD)

From here, you can perform all of the same actions available in the Quote Files area (unzip, rename, etc) as well as select a file to open it in the viewer. You can also drag it into the line item's Supporting Files section, or into the Components table of an assembly to create a new component.
