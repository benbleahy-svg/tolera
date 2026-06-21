---
title: "The BOM Builder"
slug: The-BOM-Builder
source: https://help.paperlessparts.com/s/article/The-BOM-Builder
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# The BOM Builder

> Source: https://help.paperlessparts.com/s/article/The-BOM-Builder  
> Topic: Assemblies & BOM

- Tutorial videos
  - Building a BOM from a print (without suggestions)
  - Building a BOM from a PDF (with suggestions)
  - Building a BOM from a model
- Quick start guide
- What is the BOM Builder?
- Accessing the BOM Builder
- Part type
  - Purchased components
- Working with files in the BOM Builder
  - Adding files
  - Removing files
  - Copying files
- Creating subassemblies and parts with hardware (parent/child relationships) in the BOM Builder
  - Leveraging BOMs from files
- BOM drafts
- Multiple instances of parts
- Errors in the BOM Builder
- FAQ

# Tutorial videos

## Building a BOM from a print (without suggestions)

## Building a BOM from a print (with suggestions)

## Building a BOM from a model

# Quick start guide

1. Open the BOM Builder from the Components table in a line item.
2. Add information to rows to create parts by:
  1. Typing or pasting in part numbers, and/or
  2. Assigning files to rows
  3. Accepting BOM suggestions
3. Reorganize parts and create subassemblies or parts with hardware, either by dragging rows to their destination or using click actions.
4. Assign purchased components as needed.
5. Once your BOM is complete, click “Check and Publish” to apply the BOM to the line item.

# What is the BOM Builder?

The BOM Builder is a staging area where you can enter part data, assign files, and define the tree structure for assemblies and/or parts with hardware.

On the right side of the BOM Builder is a spreadsheet-like form to enter BOM structure data. This form contains 8 columns:

- Item No.
- Part Number
- Revision
- Type
- Description
- Primary File
- Supporting Files
- Quantity

On the left side of the BOM Builder, you can access the Quote Files drawer. This area serves as a staging area for any files you need to assign to parts in the BOM.

# Accessing the BOM Builder

To access the BOM Builder for a line item, scroll down or jump to the Components table.

*When the line item does not have any child components:*

Click the blue “Build BOM structure” button to open the BOM Builder.

- If the line item has no child components yet, you’ll be asked if you want to build an assembly or a part with hardware.
  - Build Assembly BOM: the root part will be type assembly and all parts in the BOM will be manufactured by default. Choose this option if the final part will be assembled from all the items in the BOM.
  - Build Part with hardware: the root part will be type manufactured and all parts in the BOM will be purchased by default. Choose this option if the final part is a single manufactured part with purchased items (hardware/fasteners/etc) inserted.
  - Note that you can change this decision once in the BOM Builder by changing the type of the root row at any time.

*If the line item already has child components*:

Click “Edit BOM”

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E6wio)

If you assign a file that has a BOM suggestion available (likely a print or spreadsheet) to a part without child components, you will see a banner on the line item to review this suggestion in the BOM Builder.

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E706T)

To learn more about BOM suggestions, check out our article on [assistance in the BOM Builder.](https://help.paperlessparts.com/s/article/bom-extractions-and-suggestions)

# Part type

In the BOM Builder, parts can be marked as type “Assembly root”, “Subassembly”, “Manufactured”, or “Purchased”.

These types may be automatically assigned (when you’re working with a model or a file that has a BOM suggestion) or can be assigned manually, either by:

- Making a selection from the drop-down menu in the “Type” cell.
- Typing or pasting (Ctrl+C) one of the available type values into the “Type” cell.
  - Tip: You can paste a value into multiple selected cells. Select multiple contiguous cells by clicking and dragging or with Shift+click
- Selecting multiple part rows at once and choosing a type from the bulk Actions menu.
  - Select a part row by clicking on its Item No. column

A part’s type will dictate the default type of its child rows.

- If a part is an “Assembly root” or “Subassembly”, its children will be “Manufactured” by default.
- If a part is “Manufactured”, its children will be “Purchased” by default.

If a part’s type seemingly conflicts with its primary file (e.g. the part has type “Manufactured” but the primary file is a model with multiple bodies), a warning will display letting you know to review the part.

## Purchased components

Any part with the type “Purchased” must be tied to a record from your purchased component library before publishing a BOM. Parts that are “Purchased” and have not yet been assigned will have a small orange indicator letting you know they still need to tie that part to a record:

Once they are assigned, the indicator will turn green:

To assign a purchased component to a record, click into the “Part number” cell of the unassigned purchased component and search for a record in the purchased component library, either creating a new one or selecting a result.

- Tip: If you have trouble finding the record by OEM Part Number or Internal Part Number, you can use also this field to search by description.
- Like outside the BOM Builder, this will import the record’s part number and description.

If you have any unassigned purchased components in their BOM, you’ll see a button appear prompting you to “Assign [N] purchased components”. Clicking this button will do two things:

- Automatically assign any purchased components whose part number exactly matches the OEM part number of a record in your purchased component library.
- If any purchased components cannot be automatically assigned, we’ll filter the BOM to only show these purchased components so you can quickly click through and assign them.

# Working with files in the BOM Builder

Assigning files to parts in the BOM Builder is as easy as dragging them to their destination.

## Adding files

To add a new file to a BOM, first add it to Quote Files (either by uploading it from your computer or by using email forwarding). There are a few ways to assign files to rows:

- Drag and drop it to the desired row.
- Click the three-dots on the file and use the “Add to part” or “Create part” actions.
- Accept a file assignment suggestion.
  - Learn more about file assignment suggestions here.

If you assign a model with multiple bodies (likely a model of an assembly, subassembly, or part with hardware) to a row that does not have any children, we will break out its BOM underneath that row.

## Removing files

To remove files from a row in the BOM, either right-click and select “Remove” from the Actions menu or press “Backspace/Delete” on your keyboard while the file(s) are selected.

- If the file was assigned to the part from Quote Files, it will be sent back to Quote Files.
- If the file was already assigned to the part when the user opened the BOM Builder, was created by breaking out a CAD BOM, or was copied to the part from another row, it will be deleted

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E71Yn)

## Copying files

If a file should be assigned to more than one part in the BOM, simply create a copy by selecting the file(s) and pressing Ctrl+C (⌘+C on Mac) on your keyboard. Select the destination cell and press Ctrl+V (⌘+C on Mac) to paste it.

- Note that files cannot be pasted anywhere other than the “Primary file” and “Supporting files” columns.

# Creating subassemblies and parts with hardware (parent/child relationships) in the BOM Builder

If a BOM contains subassemblies or parts with hardware, you may need to add parts as children of other parts. There are a few ways you can create these parent-child structures in the BOM Builder.

Add parts directly to subassemblies or hardware to manufactured parts by hovering over the rows they want to add children to and clicking the “+” on the “Part number” cell (either “Add Child” for subassemblies or “Add purchased component” for manufactured parts).

Clicking this button will add a blank row directly underneath the part, which you can type, paste data into, or assign files to in order to create child parts.

- Tip: If you have multiple child rows to paste from a source file, pasting into a single child row will create new rows at the same level so you don’t need to add each child row manually.

To move existing parts to a subassembly or part with hardware, either:

- Drag and drop the part(s) over another part to add them as children.
  - Select a row by clicking on its Item No. cell (left-most cell)
  - Select multiple rows with Shift+Click to select a range, or Ctrl+Click (⌘+Click on Mac) to add/remove individual rows to the selection
  - Drag the selected row(s) by clicking and dragging from any selected Item No. cell.

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E720D)

- Select the “Move to parent” action (either from the row’s three-dot Actions menu or the bulk Actions menu) and select which row should become the part's new parent by clicking anywhere on the row.
  - This action can be easier than drag and drop when the child rows are very far from the row that should be their parent.

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E72TF)

If you’re working from a model, you may find that parts with hardware are incorrectly interpreted as subassembly structures. To correct these, drag the manufactured part that should be the parent over its subassembly parent or choose the “Replace parent with this part” action from the Actions menu.

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E6vBe)

## Leveraging BOMs from files

If a file contains a BOM - whether it’s a model with multiple bodies or a file with a BOM table (like a print or spreadsheet) - there are two ways to break out that BOM in the BOM Builder:

- .Assign the file to a row that does not have any children.
  - If the file is a model with multiple bodies and you assign it to a row with no children, we will break out the model’s BOM automatically and suggest the part numbers for all new child components (either from the model’s metadata or using each component’s file name).
  - If the file has a detected BOM table and you assign it to a row with no children, we will indicate that there is a BOM suggestion available for you to review by displaying the purple suggestion icon on that row. Clicking that icon will preview the suggested BOM, which you can either reject, accept, or start editing to accept.
    - Learn more about BOM suggestions here.

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E737Z)

- Use the “Replace/add children from this file’s BOM” action
  - To manually break out a file’s BOM underneath a row, right-click on the file and select “Replace/add children from this file’s BOM”.

# BOM drafts

Because the BOM Builder is a staging area, any work you do to a BOM will not be applied to the line item until you click “Check and Publish”. This allows you to move quickly and exist in states that may not be permitted outside of the BOM Builder (like having unassigned purchased components), but it also means that the BOM can exist in one state in the BOM Builder and another in the line item. There are a couple of things we do to mitigate the potential conflicts/confusion this can cause and preserve your work while your BOM is in progress.

- Each time you makes an edit to the BOM, a draft of your work will autosave.

![](/servlet/rtaImage?eid=ka0Ns00000069IL&feoid=00N5G00000WB8Hk&refid=0EMNs00000E73E1)

- If you exit the BOM Builder for any reason while you have a draft in progress, the BOM Builder will open with the most recent draft state loaded.
  - At any time, you can discard your current draft to return the BOM to its current state in the line item.

- While an unpublished draft is in progress in the BOM Builder, actions outside of the BOM Builder that would alter the contents of the BOM Builder will be disabled. To enable these actions, open the BOM Builder and either publish or discard your BOM.
  - Actions like “Replace subassembly with manufactured part” or “Make assembly”, as well as adding and deleting a line item’s files, will be disabled until the BOM Builder draft is either published or discarded.

# Multiple instances of parts

If a part exists multiple times within an assembly, these instances need to be linked so you only need to cost them once. There are a few ways that multiple rows can be linked as the same part in the BOM Builder.

- The parts were generated by breaking out the BOM of a CAD file.
  - In this case, we can use the CAD file’s BOM structure to automatically determine which components were the same part.
- You copied one part’s entire row and pasted it to another location in the BOM.
- Multiple rows in the BOM have the same exact same part number and revision and no conflicting information; when you check the BOM or check and publish, these rows will be linked as the same part.

When you’re editing a part that exists more than once in an assembly, we’ll indicate how many other rows will be impacted by your changes.

If you make a change to a part that exists in multiple places but aren’t directly editing it (ex. by pasting data or adding child components to a row), we’ll provide a toast letting you know all instances of the part have been updated.

Note that two instances of the same part cannot exist at the same level of a BOM. You cannot move one instance of a part to a level that already has an instance of that part; instead, delete one instance and change the BOM quantity for the other.

# Errors in the BOM Builder

When you publish your BOM or perform the manual “Check BOM” action, we’ll check the structure to see if anything about the BOM structure is incompatible or cannot exist outside of the BOM Builder.

- E.g. Two rows have the same part number and revision but different descriptions or primary files, a row has a description but no primary file or part number, etc.

If we identify an error in the BOM, we won’t publish your draft and will provide an error message at the top of the BOM Builder letting you know which item numbers have resulted in the error.

Once you have resolved the error, you can attempt to publish their BOM again. If there are any other unresolved errors, these will be communicated and prevent the BOM from being published until they have all been resolved.

# FAQ

Can I import an Excel file to the BOM Builder?

- If you have an Excel file that contains a BOM, we’ll analyze it on upload to see if we can extract and suggest a BOM from its contents. To see this suggestion, assign it to a row that does not have any child components. The suggested BOM will be broken out underneath the row.
  - Learn more about BOM suggestions here.

Where do I add materials in the BOM Builder?

- While a bill of materials can sometimes include both parts and the materials consumed by those parts, the BOM Builder is exclusively designed for building a part’s product bill of materials (the parts that go into the assembly, not the raw material stock consumed by these parts).

How many parts can I add to a BOM in the BOM Builder?

- Users can work with up to 1000 unique parts in the BOM Builder. That means that if the same part exists in more than one subassembly or area of the BOM, it will only count toward this number once.
  - If you are exceeding the limit while building your BOM but you know it contains 1000 or less unique parts, try clicking Check BOM which will consolidate the count of parts that exist multiple times.

Can I change the columns? (Rename or add custom columns)

- The columns in the BOM Builder are not configurable, but they can be resized by clicking and dragging the edges of the header cell. To return a column to its default size, double click the edge of the header cell.

How are purchased components matched to records in the PC library?

- If a purchased component’s part number exactly matches the OEM part number of a record in your purchased component library, we will assign it to that record when you click the “Assign purchased components” button. If you’re manually assigning purchased components (by clicking into the part number cell and typing to search your library), we will return results that have matching content in the purchased component description, OEM or internal part number, and any custom columns you may have set up.
