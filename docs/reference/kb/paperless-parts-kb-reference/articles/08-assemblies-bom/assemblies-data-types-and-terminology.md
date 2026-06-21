---
title: "Assemblies- Data types and terminology"
slug: assemblies-data-types-and-terminology
source: https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Assemblies- Data types and terminology

> Source: https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology  
> Topic: Assemblies & BOM

This article explains the data types and terminology associated with assemblies in Paperless Parts. For a more holistic explanation of our approach to assembly parts, and a guide to quoting them, check out our [Intro to the assembly toolkit](https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit) article.

## Parts & assemblies

**Parts** are any physical thing designed for a specific form or function. **Assemblies** themselves are parts, and consist of a structured collection of multiple individual parts that get put together. When designing and manufacturing assemblies, it is important to organize the different lower level parts, which we will refer to as **child parts**, into a structural hierarchy of parent-child relationships beneath the top level part, or the **root part**. This structural hierarchy, or **tree**, helps with design efficiency and manufacturing accuracy.

Let's walk through an example of an assembly to illustrate how assemblies work in Paperless Parts. Let's say we need to manufacture this assembly:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f02ae961ff5d5f24f99964/file-rO60gxsT6X.png)

In this assembly, the top level part, otherwise known as the **root part**, is called "Top Level Frame". There are four lower-level parts, or **child parts**, including a subassembly called "Base Frame", and three unique manufactured parts named "Saw Cut Part", "Short Miter Cut Part", and "Long Miter Cut Part" colored red, yellow, and gray respectively. These parts are listed in alphabetical order in the flat BOM with their associated flat quantities, or how many times they appear in the entire assembly, in the above screenshot.

## Nodes

When building an assembly, there are potentially dozens of different part numbers that need to be manufactured or purchased and then assembled together into the final product. A lot of these part numbers will have dependencies on other part numbers. We need a mechanism to take that flat list of part numbers and tie them together in a structure to help us visualize and manage those dependencies. The best way to do this is to build a dependency tree. We essentially need to take a flat list of part numbers like we see on the left, and turn it into a tree of parts like we see on the right:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3c19d4181f8597e7d1223/file-HalRThx9dl.png)

To build the tree structure, we use **nodes**. A **node** is an occurrence of a part within a tree. A node describes the *location* of the occurrence in the tree by specifying its parent node. A node describes the *quantity* of the occurrence in the tree by specifying a quantity relative to the parent node. The multi-level BOM in the part viewer is actually the list of nodes in the tree:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3d1d561ff5d5f24f9aa7e/file-dyUslYgY5L.png)

**Note**: The **root node** is special, and has no parent node and always a quantity of one.

The flat BOM in the part viewer is the actual list of unique **part** objects in the tree structure, presented in alphabetical order. Here is how the multi-level BOM and flat BOM relate to each other in this example:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3d47b80fd5a31e7ad0f1d/file-mXQBjtfHYv.png)

If a single part has multiple nodes within an assembly tree, the same underlying part data will be linked to all nodes. In the above example, even though there are two nodes of "Saw Cut Part" in this part tree, there is only one part object that is referenced in the two occurrences. We see this concept reflected in the multi-level BOM in the part viewer. When you select a node of "Saw Cut Part", all other nodes that are linked to this part will also be highlighted:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3d3606d67192dc61b99bb/file-Db3VueCjHw.png)In the flat BOM, you can see we only have one part object focused, and its flat quantity captures all quantity contributions from its two separate nodes:
 ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3d57461ff5d5f24f9aa97/file-KtpJOBwi6D.png)

The primary reason why we structure the data like this is so you do not have to re-quote the "Saw Cut Part" multiple times. We will see how this works in the next section.

## Components

So now that we have our part structure, we want to quote it. When quoting a part structure, Paperless Parts uses another layer of data called **components**. A **component** is a part with pricing information, where things like materials, operations, and customer requested quantities are stored. You interact with component data in the quotes page. A component's materials and operations refer to the information stored within a part, such as its geometry, to drive the costs that get calculated. The diagram below explains how components relate to parts:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3d9a961ff5d5f24f9aacc/file-EAFiJMjWBC.png)

**Note**: The **root component**, in orange above, is essentially equivalent to a quote item. A quote item simply links a root component to a quote with a position in the quote. When you expand a quote item in Paperless Parts, you are looking at the data stored on the root component. All other components, colored yellow above, are **child components**. All the costs from child components roll up the tree structure to the root component.

On components, you will do things like assign a process, add materials, and add operations. On the root component, you will also do things like add customer requested quantities, add pricing items, add add ons, and add expedites. Similar to parts, it is important to have a tree view of components when quoting to help keep things organized. The tree view beneath the expanded quote item is an equivalent view to the multi-level BOM in the part viewer, except it is tying nodes to components instead of parts:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3db226d67192dc61b9a0a/file-cUaq2zByVs.png)The tree of component nodes relates to the flat BOM of components in this way:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3e67861ff5d5f24f9ab14/file-CLlbqjebC7.png)

When you have toggled to the Child BOM display of the BOM, you are viewing the component nodes directly beneath the root component:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3e68f829a3853b6925718/file-gwOmDpSDWG.png)Similar to the Child BOM display of the root component, the Child BOM display of any subassembly will show only the component nodes directly beneath the subassembly:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3e6ad6d67192dc61b9a3f/file-xpcY9zMIUq.png)Similar to functionality we saw in the multi-level BOM in the part viewer, when you click to expand child components in the assembly tree, it will show you all nodes of the component in that tree. Let's look at what happens when we expand the "Saw Cut Part" component:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f3e76b829a3853b692571e/file-sDkifBdZfs.png)

What this means is that you will only have to configure the pricing on a child component once regardless of how many times it appears in the BOM structure. You will notice above that the Make Qty is 6 for this component for a customer requested quantity of 1, and not 2 or 4. The system will intelligently calculate the total number of pieces you need to make for each child component based on its location in the tree and the customer requested quantities. This total make quantity will then be passed into the material and operation formulas to calculate costs.

**Note**: When looking at the BOM in the context of a quote, it is important to understand that while you are working with components, the structure of the components, and the parent/child relationships between them, are defined with nodes and parts. The Child BOM and assembly tree of components are really just views of component data that sit on top of the underlying part and node data.

## Building part structure when quoting

Within a quote item, you will see many BOM building actions such as adding new components, adding new subassemblies, moving BOM levels up and down, deleting nodes, and others. When performing these actions, you are actually editing the structure of parts and nodes, while also making changes to components. Let's walk through an example to demonstrate how this works.

Let's say you want to add another manufactured component to the "Base Frame" subassembly. It will have the part number "Sample Part" and a node quantity of 1:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f0290e5c214850abad41ba/file-tsF2C6hPZp.gif)

When you are performing this action, you are actually doing three things:

1. Creating a new part
2. Creating a new node that ties the "Sample Part" part to the "Base Frame" part
3. Creating a new component to store pricing information associated with "Sample Part"

Let's illustrate this action by illustrating the data objects with a diagram:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/62f0292b6d67192dc61b88e6/file-LUzo846K44.png)

This concept extends to all BOM building and editing actions. Here are some additional examples walking you through what data gets created/edited associated with user actions.

When uploading a CAD model to a quote, the system is:

1. Creating parts for each unique geometry found in the model
2. Creating nodes to connect those parts together, mirroring the tree found in the file
3. Creating components that link to each part
4. Setting up other information you may have specified on upload, like customer requested quantities

When adding a part to a quote from the part library (that you have not quoted before), the system is:

1. Creating components for each part in the tree
2. Adding a customer requested quantity of 1 on the root component

When moving down a BOM level, the system is:

1. Changing the parent node on an existing node to a node one level lower in the tree
2. Recalculating the BOM quantity on the child part based on its new location in the tree
3. Recalculating the deliver and make quantities on the child component based on its new location in the tree
4. Recalculating pricing for the child part, the new parent component, and any other ancestors back up to the root component

Please refer to other knowledge base articles for more information on what is possible when it comes to BOM editing in Paperless Parts.

## Summary of terms

- Part: any physical thing designed for a specific form or function
- Assembly: also a part, and consist of a structured collection of multiple individual parts that get put together
- Root part: the top-level part in an assembly
- Child part: any part in an assembly that is not the root part
- Tree: a display of the structural hierarchy of parent/child relationships between parts
- Node: an occurrence of a part in a tree. It describes both the location and quantity of the occurrence. It describes the location of the occurrence by specifying a parent node. It described the quantity of the occurrence with a count relative to its parent node.
- Root node: a special node in the tree that is always linked to the root part. It has no parent node and always has a quantity of one.
- BOM: stands for Bill of Materials. There are multiple different BOMs in Paperless Parts. A BOM is a way to communicate data found in assemblies. It is best to think of BOMs as a view of data instead of the data itself.
- Component: a part with pricing information. Information on materials, operations, and customer requested quantities lives on a component.
- Root component: the component that is tied to the root part in the tree. The root component is special for three primary reasons:
  - It is the only component where you configure pricing items, add ons, and expedites
  - All the costs from child components in the tree roll up to the root component
  - Information on the root component is shown to the customer on the digital quote
- Quote item: this ties a root component to a quote quote. It is equivalent to a root component in the UI of Paperless Parts. When you are expanding a quote item, you are looking at the data of the root component.
- Child component: any component that is not the root component in a tree
- Flat Qty: is the total count of a part/component in an assembly for a customer requested quantity of 1
