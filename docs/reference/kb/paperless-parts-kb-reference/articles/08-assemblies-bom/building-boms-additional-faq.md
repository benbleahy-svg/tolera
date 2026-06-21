---
title: "Building Boms - Additional FAQ"
slug: building-boms-additional-faq
source: https://help.paperlessparts.com/s/article/building-boms-additional-faq
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Building Boms - Additional FAQ

> Source: https://help.paperlessparts.com/s/article/building-boms-additional-faq  
> Topic: Assemblies & BOM

#### Where can I find an intro to how assemblies work?

##### [Check out this article](https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit).

#### What does the term "node" mean?

A node is an occurrence of a part within a tree. A node describes the *location* of the occurrence in the tree by specifying its parent node. A node describes the *quantity* of the occurrence in the tree by specifying a quantity relative to the parent node. Each row in the multi-level BOM in the part viewer can be thought of as a node. Refer to the [intro to assemblies article](https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology) for more detail.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f12d8d5c214850abad451e/file-yHoXA2jV74.png)

#### What is the difference between a "part" and a "component"?

In the part viewer and in the part library, you are working with parts. Parts store file data and assembly tree structure. In the quotes page, you are working with components, which are essentially just parts with pricing (materials, operations, customer requested quantities, etc.). Every indentation in the assembly tree in the left panel of the quotes page is actually a node in the multi-level component BOM. Each row in the child BOM is also a node. Refer to the [intro to assemblies article](https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology) for more detail.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f12facffff0c4e1783fb31/file-VV84tiifi1.png)

#### If the same geometry appears more than once in the CAD model, will I have to quote it twice?

No. The system will create a single instance of a part for each unique geometry it sees in the CAD model. The system will then place nodes of this part at the proper locations with proper quantities in the assembly tree. All the nodes of this part, and when quoting it, its component, will share all underlying data with each other. Pricing will be based on the total quantity of the component found in the entire assembly for each respective customer requested quantity.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f12ff080fd5a31e7ad0181/file-BlE6SGEjI9.png)

#### How can I see if there are multiple nodes of a part within an assembly structure?

You can use the multi-level BOM in the partviewer. All nodes of the part will be highlighted in blue when they are selected. You can also use the assembly tree in the quotes page in the left panel. When expanding a component, the tree will automatically expand and highlight in blue all nodes of the part.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f1301161ff5d5f24f99ce7/file-4Gb0Mixy3q.png)

#### Can I modify the BOM structure that comes from the CAD model?

Yes, you can. [This article explains it in more detail](https://help.paperlessparts.com/s/article/editing-the-cad-extracted-bom). You can use the move up a BOM level and move down a BOM level tools to edit structure. You can also add manual components and subassemblies, delete existing nodes, and edit the quantities of nodes in the child BOM. All of these actions are available in the child BOM view. You need to be in the child BOM because you need to specify which parent component these changes are happening relative to.

#### How will adding a child subassembly file affect the BOM structure?

Uploading an assembly CAD file as a child component will create a new subassembly within the original BOM. The CAD structure of the new file will be broken out as a subassembly in the BOM.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6363d6b668af3518960f782d/file-ODkM07aleF.gif)

#### Why should I edit the CAD-extracted BOM instead of building the BOM manually from scratch?

Leveraging the CAD-extracted BOM gives you a starting point to work off of that will prevent mistakes and allow you to finalize the BOM faster than if you were building it manually. The larger the BOM the more benefits you will get. Also, when using CAD, your geometrically driven pricing formulas can leverage all of the benefits of Paperless Parts geometric analysis. Your formulas can use geometric properties like volume, area, dimensions, bend count, volume removal, etc. without you needing to input those numbers manually.

#### When editing the BOM in the quotes page, will that change the BOM in the part viewer?

Yes. When you are editing the BOM in the quotes page, you are actually editing the structure of parts that sits underneath the components that store all pricing information. The BOM tab in the viewer and the BOM you see in the quotes page will have the same structure. Check out [this article on assemblies](https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology) for more details.

#### When editing the BOM in the quotes page, will that change the CAD tree in the part viewer?

No. Edits to the BOM will not affect the CAD tree. We will always present the same CAD tree structure originally found in the file when viewing the CAD model in the viewer.

#### Can I edit the BOM in the part viewer?

No. This is functionality we hope to add in the future.

#### Is there a way for me to restore the structure found from the original CAD file in case I mess things up?

No. If you truly want to start over, you should just re-upload the original file. If you simply want to check your structure against what was originally in the file, you can always open up the part viewer and look at the CAD tree and compare that structure against the one you have modified in the BOM tab of the viewer.

#### How can I manually assign an assembly? What do those 2 checkboxes mean?

Perhaps a customer sent you a file with several assembly components buried in the PDF, or you have multiple single-component part files that you know will need to be assembled. [This article](https://help.paperlessparts.com/s/article/quoting-an-assembly-part-from-a-pdf) covers how to perform this action and explains the checkboxes.

#### How can I convert an assembly to a normal single-component file?

You can not convert an assembly to a non-assembly, even if you delete all components except for one. If you wish to quote just one component from an assembly file, you can extract that component to a separate line item. This article explains in more detail.

#### How do I download individual part files from an assembly CAD model?

Users cannot download individual components from an assembly CAD model. In other words, if you upload ONE 3D file that contains the entire assembly, we cannot export individual part files within the platform. This would need to be done in your CAD system. Any manually added parts in the BOM structure that you have uploaded as separate files will be downloadable. As a rule of thumb, you always have access to download exactly what you uploaded. Nothing more, nothing less.

#### How do I switch primary files on assemblies?

You can switch the primary files for any manually added child part. You cannot switch primary files on parts if they were extracted from a single CAD model. [This article](https://help.paperlessparts.com/s/article/flexible-primary-file-assignment-june-13th-2022) explains this in more detail.

#### Why am I getting a "You cannot _____ because this part is shared between multiple quote items; to do so, deep copy."?

Parts can be quoted multiple times, and the quoted version of a part, a component, will share the part data between these multiple quote items. So if you wish to edit information that lives on the part, like BOM structure and the primary file, you must deep copy the quote item in order to create a fresh copy of the underlying part structure to modify. [This article](https://help.paperlessparts.com/s/article/deep-copy-replace-referenced-part-faq) explains this in more detail.

#### Can I extract a subcomponent from an assembly out to its own line item?

Yes. You can use the move up a BOM level tool to pull any subcomponent out into a separate line item that you can quote separately. [This article](https://help.paperlessparts.com/s/article/quoting-children-of-assemblies-as-separate-parts) explains in more detail.

#### Are the extracted subcomponents linked back to the components in the original assembly?

No. When components are extracted from the assembly, they create entirely new part and component objects. The pricing is not shared between them. They are, however, referencing the same underlying file geometry.

#### Can I download the subassembly or subcomponent files after I extract them to their own line items?

No. Downloading the file from the extracted line item will download the original uploaded file.

#### If I merge two quote items into the same assembly, and some of their child parts have the same part number, will the system automatically merge them together?

No. The child parts from separate line items are completely unlinked.
