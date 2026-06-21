---
title: "BOM in viewer - April 17th, 2022"
slug: bom-in-viewer-april-17th-2022
source: https://help.paperlessparts.com/s/article/bom-in-viewer-april-17th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# BOM in viewer - April 17th, 2022

> Source: https://help.paperlessparts.com/s/article/bom-in-viewer-april-17th-2022  
> Topic: Release Notes (What's New)

## What's new in v23.0.0

We are excited to announce a new **major version release** of Paperless Parts. We have made a big leap forward in making it easier to interact with CAD and BOM structures in Paperless Parts. We have simplified the user experience when interacting with assemblies in the partviewer, especially for assemblies that are manually constructed.

The release consists of four major highlights:

- A new multi-level and flat BOM display of the part structure in the partviewer
- Clearer interactions with manually constructed assemblies in the partviewer
- Ability to view CAD structure for assemblies uploaded as supporting files
- Significantly decreased partviewer load times for CAD files

### BOM in viewer

The new BOM tool within the partviewer is the most exciting update shipping with this version. We have introduced a multi-level and flat BOM tool allowing you to navigate the part structure much more effectively. Here is a video summarizing the changes:

### Manual assemblies improvements

We have simplified the interactions with manually constructed assemblies in the platform. The video below explains the details:

**Note**: All manually constructed assemblies created prior to this release will have this new presentation in the partviewer. It will not have any effect on pricing or integrations.

### See assembly CAD structures everywhere, every time, for everyone

There are three specific situations where the behavior with uploaded assembly files is different. These three situations are when uploading assemblies as supporting files, when deleting a part from a BOM that was created automatically from an assembly file upload, and when uploading assembly files as manual components. All three of these situations are related to the concept of the Paperless Parts viewer showing the original representation of the CAD file. Regardless of where or how a file gets uploaded to the site, or the downstream manipulation of data related to that file, we wanted to make sure that we always showed the original CAD representation stored in that file. As a result, when uploading assembly files as supporting files or as manual components, you will now be able to see a CAD structure in the viewer. When deleting a component from the BOM in a quote item that was generated automatically from an assembly file upload, you are just deleting the component that *references* a certain CAD geometry. You are not actually removing that CAD entity itself from the structure in the viewer (like we previously did). As a result, the CAD tree in the viewer will still present the geometry representation of the BOM items you have just deleted. The video below explains the details:

**Note**: If your account does **not** have the assemblies quoting functionality available, all uploaded assembly files **will still generate** a CAD structure in the partviewer for viewing. However, only one item will be created in the BOM in the partviewer and only one item will be created in the BOM in the quote item. If you are interesting in quoting assemblies, please reach out to support@paperlessparts.com.

**Note**: Assembly files that were previously uploaded as supporting files will **still****not** have a CAD structure. You will need to re-upload those files to see a CAD structure.

### Decreased partviewer load times

The last major improvement to highlight is significantly decreased partviewer load times for CAD files. You can expect a ~25% faster load time for CAD files on first load, and a ~50% faster load time for CAD files on second load. The term "second load" means any request to open a CAD file in the viewer after recently loading in the same geometries. We have implemented a memory caching mechanism where we can rapidly load data from your browser's cache if it has been loaded recently. This will come in handy when working with assemblies and when switching back and forth between viewing different quote items. The video below will illustrate the improvements. The left side of the screen is showing you the application running with the updates from v23.0.0. The right side of the screen is showing you the application running prior to these changes.
