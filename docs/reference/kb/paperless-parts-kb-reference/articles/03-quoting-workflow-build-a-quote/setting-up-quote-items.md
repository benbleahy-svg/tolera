---
title: "Setting up line items"
slug: setting-up-quote-items
source: https://help.paperlessparts.com/s/article/setting-up-quote-items
topic: "Quoting Workflow (Build a Quote)"
captured: 2026-06-19
---

# Setting up line items

> Source: https://help.paperlessparts.com/s/article/setting-up-quote-items  
> Topic: Quoting Workflow (Build a Quote)

Once you've created a quote, add a line item for each part you need to estimate from the RFQ. In this article, you'll learn how to create, set up, and manage line items.

#### **On this page**

- Creating line items
  - Create new line items from Quote Files
    - Create line items in bulk
  - Create new line items by uploading part files
  - Create new blank line items without a file
  - Import historical work to a quote
- Managing line items
  - Bulk edits
  - Merging line items
  - Removing a line item
  - Reordering line items
  - Drag and drop
- Line item-level information
  - Uploading supporting files
  - Adding geometric attributes
  - Changing customer-requested quantities

---

# Creating line items

To add the part you're estimating to a quote, you'll need to create a line item. Line items are the central location for all of the costing, pricing, and estimating information related to a part.

There are four ways to create a line item, depending on how you created the quote and if the part is repeat.

*For new parts:*

- Create new line items from Quote Files
- Create line items in bulk
- Create a new line item by uploading part files  from your computer
- Create a new blank line item without a file

*For parts that your shop has previously quoted (or uploaded into Paperless Parts):*

- Import historical work as a new line item.

*Tip*: Not sure if you've quoted a part in Paperless Parts before? Try searching by part number, PDF text, notes, and more in the **Search anything** bar.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63ee9ae47a31233f59f6ddf1/file-8AIcxJanzl.png)

## Create New Line Items from Quote Files

If you created the quote using [email forwarding,](https://help.paperlessparts.com/s/article/creating-a-new-quote)  the files from the RFQ email will be in Quote Files. You can also upload files from your computer to Quote Files so you can unzip compressed files and manage your files in one place. Learn more about managing Quote Files [here](https://help.paperlessparts.com/s/article/New-actions-for-Quote-Supporting-Files-August-31st-2023) .

**If you have a quote with only a few line items, drag your quote files into the navigation bar to create line items:**

1. Select the file(s) you wish to move to quote files
2. Drag files into the navigation bar
  1. Or, click **Actions** --> **Create new line item per file**
3. Enter the relevant information
  1. Part number and revision (if you are moving one file)
  2. Customer-requested quantities
  3. If you are moving more than one file, you can [merge files with the same filename](#merge-files-with-same-filename)
4. Click **Create Item(s)**

Continue dragging Quote Files into the navigation bar or directly onto existing line items to add the files as supporting files or components until your line items are set up.

*Tip:*Got some Quote Files that are child components or supporting files for child components? Leave these files in Quote Files and add them to your assembly later in [the BOM Builder.](https://help.paperlessparts.com/s/article/The-BOM-Builder)

## Create New Line Items in Bulk

**If you have many line items, we recommend creating line items in bulk.**

Click **Bulk create line items**in the navigation bar. If you create the quote from an email RFQ, we may recommend line items based on the contents of the email. Learn more [here](https://help.paperlessparts.com/s/article/Quote-Setup).

![bulk create suggestions.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs0000039DIr)

**Copy/paste** from your RFQ files or a spreadsheet, or **type in** **part numbers, revisions, descriptions, and quantities** into the spreadsheet-like interface. Click **Create Line Items**to create blank line items.

![bulk line item gif.gif](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002r2wz)

Based on filenames and AI suggestions, files in Quote Files will be automatically analyzed to determine if they belong to one of the line items created. Click **Add to line items** to move the files into their matching line items:

![fileassignment automation.gif](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002r3Ej)

Any files that are not assigned to line items can still be manually added to existing line items by dragging them from Quote Files or your desktop onto the corresponding line item:
![dragmanualpart.gif](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000003DdbJ)

Files can be converted back to Quote Files by clicking **Move to quote files** or by **dragging back to quote files**

![move to quote files.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002r3Hx)

## Create New Line Items By Uploading Part Files from Your Computer

If you did not create a quote using email forwarding and prefer to create line items directly from files on your computer, you can upload the files as new line items into your quote in Paperless Parts.

Click **Add line item** at the bottom of the navigation bar and select **Upload files:**

![upload files.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qn1x)

Chrome users can also drag and drop files directly onto the navigation bar or at the bottom of the quote.

*Tip:*Files not coming in as expected? Try downloading the files to your local server before dragging and dropping them to ensure that the information is imported correctly. You should also confirm that all file types are [supported by our platform](https://help.paperlessparts.com/s/article/supported-file-types).

Once you upload your files, a window will appear prompting you to select the following for your part:

- Part number and revision (optional, only if you are uploading one file)
- Customer-requested quantities (required, this will default to 1)
- ITAR status (optional)
- If files with the same filename should be merged into one line item (only if you are uploading multiple files)
  - If you leave this option checked and upload multiple files with the same name but different types  (ex. bracket.STP and bracket.PDF), they will automatically be bundled as a single quote item with the model as the primary file. If you uncheck this option, each file will create a separate quote item.
  - If you accidentally create multiple quote items because of a mismatch in naming, merge them into a single quote item  after uploading.
- If you want to be able to enter process, material, and finish when uploading new files as line items, go to Settings --> Quote Creation --> Line Item Settings (or go to this link).

Hit **Confirm** to create the line item(s)

## Create a New Blank Line Item Without a File

If you don't have any technical files for the part that you're quoting, create a blank line item which adds a part without files to your Part Library. Part files you may receive down the road can be attached as supporting files at any time.

Click the **Add line items** button at the bottom of the navigation bar and select **Create blank line item**.
![create blank line item.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002quUn)

## Import Historical Work to a Quote

For parts you have previously quoted or added to Paperless Parts, use the **Import Historical Work** option to quickly import part information, costing, and pricing data as a new line item.

To import a historical line item, click the **Add line items** button at the bottom of the navigation bar and select **Import historical work**.

![import historical work.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qjj5)

Search the interface for the part number you wish to import. Use the **Search part number only** and **Include child parts** toggles to refine search results.

- Toggle **Search part number only** off to expand your search by file name, quote number, and RFQ number.
- Toggle **Include child parts** on to include children of assembly parts in search results.

Select a result to preview part information, costing, and pricing data from the historical quote or job.

![](https://lh5.googleusercontent.com/juQ6UYV0hmtqZligbwb1RpedSKF5sUH7zuPX2267X-8Yu8Lx1gsO6mevnS23YS43uEE0o0o4WCvFfgxnuubky1ioP3Bz37EAZXmxFzIoE9svag5NtJ8lr2M2xawl_WHELt94X4FhSsNKP9MDHzQ3rA)

*Tip*: Hover over the (i) next to the Costs bar to see a dollar value for each color of money.

Once you have selected the item you wish to import, click**Import item**.

- If you want to import more than one part at a time, check **Import another item** before importing your selection. (This will determine if the window stays open or closes after you import the first item.)

![](https://lh3.googleusercontent.com/ZC6g8wpJecq0Ikrn8hT3FHHdBrAKIu10dHFyPGjJOFgaSzmZooALHa0NA8yp5JupZxi0os7ZzzFhpTJdGz9jN9qn6AvlFKd-UvK9l1VOMehTInG6kURehayV_f-8IpDZM4BO1CBdWsaVJE29s5OUQw)

The selected item will be added to the quote as a new line item, complete with all relevant data from the historical quote or job.

# Managing Line Items

Existing line items can be edited, merged, removed, and reordered from the left-hand navigation bar.

## Bulk Editing Line Items

To edit the process, material, or finishes for multiple line items:

1. Select all quote items you'd like to edit using the checkboxes on the left of the navigation bar.
2. Click **Actions** and select **Edit process/material/finish.**
3. Enter the process, material, and finishes you wish to apply to all selected line items. This will replace existing data.

To edit the customer-requested quantities for multiple line items:

1. Select all quote items you'd like to edit using the checkboxes on the left of the navigation bar.
2. Click **Actions** and select **Edit quantities.**
3. Select if you wish to "Add quantities" or "Replace all quantities"
  1. Add quantities: add the entered quantities to the existing quantities for all selected line items
  2. Replace all quantities: replace the existing quantities with the entered quantities for all selected line items
4. Enter the quantities

![Screenshot 2024-02-02 at 4.54.30 PM.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qkqS)

## Merging Line Items

To merge line items into a single line item as supporting files or child components, drag the line items into the existing line item just like you do when adding files to folders on your computer:

## ![draganddroptomerge-ezgif.com-video-to-gif-converter.gif](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qwTN)

You can also merge line items using the **Actions** menu:

1. Select all line items you'd like to merge using the checkboxes on the left of the navigation bar.
2. Click **Actions** and select **Merge quote items as supporting files**or **Merge quote items as components**.

![merge action menu.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qwI5)

1. Select which line item you will be merging the other parts into.
  1. If merging as supporting files: The part files associated with whichever line items you do not select will become supporting files in the new line item.
  2. If merging as components: All parts that are not the root part will become child components in the new line item, with their supporting files preserved as supporting files of the new child components.
2. Click **Merge Items** to confirm.

## Removing Line Items

When removing a line item from a quote, you can either move the files back to Quote Files or remove them entirely from the quote.

Remove line item(s) and move files back to Quote Files by selecting the line item(s) in the navigation bar and dragging into Quote Files.

![remove from quote drag and drop.gif](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qtX9)

Or, remove line item(s) and remove the files from the quote:

1. Click the three dots to the right of the part in the navigation bar.
2. Select **Remove from quote.**

![remove from quote.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qtqU)

## Reordering Line Items

To change the order in which line items will be presented on the quote, click and drag the line item in the navigation bar. You can also select multiple line items and drag them all to a new location in the navigation bar.

![reorder.gif](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qlRW)

## Drag and drop

You can easily move files into and around a quote by dragging one or more files and dropping them to other areas of the quote:

![quote files drag and drop.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000003Dduf)

# ![line items drag and drop.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000003DdwH)

# ![expanded quote files drag and drop.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000003Ddxt)

![assembly component drag and drop updated.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000003De17)

# Line Item-Level Information

To open a line item:

Just like quotes, line items have fields you can fill out with relevant part data. The info you add here will remain with the part, making it easy to reference if you ever need to requote it.

1. Select the part in the navigation bar **or**
2. Click on the part in the main quote area.

![Screenshot 2024-02-02 at 5.16.29 PM.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qxHN)

Within the line item, assign a part number, revision, and part description and add detail in the Manufacturer's notes fields. Learn more about how Paperless uses AI to assist you in filling out Part Number, Revision, and Description [here](https://help.paperlessparts.com/s/article/Found-in-files-extractions). Note Manufacture's Notes will visible to the customer on the quote, as indicated by the open-eye symbol next to them.

![Screenshot 2024-02-02 at 5.22.51 PM.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qxfZ)

## Uploading Supporting Files

To attach supporting documents to this part, either drag and drop files into the Part Files section or click **Upload Files** to browse your local server.

![supporting files.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qxin)

*Note*: Although we [support many file types](https://help.paperlessparts.com/s/article/supported-file-types), we are able to read the most geometric information from CAD files and 3D models (especially STP files). If you have one for a part, be sure to assign it as the primary file - otherwise, we won't be able to automatically pull in geometric attributes or perform geometry-based calculations.

Learn more about primary and supporting files [here](https://help.paperlessparts.com/s/article/swap-primary-and-supporting-files).

## Adding Geometric Attributes

If you don't have a model (maybe you're just working off of a PDF or in a manual part), be sure to enter geometric attributes for the part. Many operations and cost calculations rely on these values.

1. Click Actions --> **Edit geometric attributes**.

![geometric attributes.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qurO)

1. Enter the maximum X, Y, and Z dimensions of the part.
2. Enter the volume, either as a raw value or by removal %.
3. Add the surface area.
4. Click **Accept changes** to confirm.

*Tip:*Use the "Swap units" button to enter values in inches or millimeters.

![](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs00000GK9fR)

## Changing Customer-Requested Quantities

To add or adjust customer-requested quantities for a part, click **Change quantities**.

![Change quantities.png](/servlet/rtaImage?eid=ka0Ns0000006K8v&feoid=00N5G00000WB8Hk&refid=0EMNs000002qyJt)

Or, change quantities for multiple line items using [bulk actions](#bulk-editing-line-items).

You can also assign a **Most likely to win** percentage to each quantity. Setting this value can be helpful if you're using our Analytics feature to predict revenue. (*Note*: This is an enterprise-level feature.)

Click **Save changes** and **Confirm** to apply the new quantities, but remember that if you have already made any overrides to a part's costing, this may impact/remove them.

The next step is to [assign a process](https://help.paperlessparts.com/s/article/assigning-a-process-material-and-finish) (if you haven't already) and add [costing](https://help.paperlessparts.com/s/article/costing-a-part) to your quote item. Or, if any of the line items are assemblies that need to be manually built out, check out [how to build an assembly part with PDFs.](https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-pdf)
