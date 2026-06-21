---
title: "Quoting a part with hardware from a model"
slug: quoting-a-part-with-hardware-from-a-model
source: https://help.paperlessparts.com/s/article/quoting-a-part-with-hardware-from-a-model
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Quoting a part with hardware from a model

> Source: https://help.paperlessparts.com/s/article/quoting-a-part-with-hardware-from-a-model  
> Topic: Assemblies & BOM

Although Paperless Parts can extract the component quantities and structure of an assembly from a CAD file, we are not able to automatically distinguish which parts are manufactured components and which are hardware. Because of this, a model with more than one component will come into Paperless marked as an assembly even if it is actually a single-component part with hardware. This creates an extraneous "top-level" part number. This article will walk through best practices for quoting a part with hardware from a CAD file, including how to remove the extra part number.

# Video walkthrough

# Written walkthrough

## Upload the CAD file

Start by uploading the CAD file for your assembly part into a quote to [create a new quote item](https://help.paperlessparts.com/s/article/setting-up-quote-items#h.y0w06dog8ooi). To ensure that the file loads correctly, follow our upload instructions [here](https://help.paperlessparts.com/s/article/supported-file-types#pack-n-go).

Once you upload your file, a **Create Line Item** window will appear, prompting you to select a process, material, finish, and quantity for your part.

If you know you're quoting a part with hardware, we suggest not selecting a process until *after*you correct the BOM structure. Sometimes, [costing can be affected by a part's assembly status](https://help.paperlessparts.com/s/article/intro-to-the-assembly-toolkit#h.nys9v6p1vafn), so it's always best to be confident in your BOM structure *before*performing any costing.

Click **Confirm**to create the quote item and proceed.

## Convert to manufactured component

Once the part has loaded, convert the assembly part to a single-component part with hardware with the **Replace assembly with manufactured component** action.

1. Click the three dots next to the part you want to convert in the navigation bar.
2. Select **Replace assembly with manufactured component**. This will open the BOM restructuring drawer.

![](https://lh3.googleusercontent.com/4Lw0jVf_t9_6hk0lu7to1ASkgKJlFrJ9t_f5dywhPhqSXtVzNv9M3mbtREQhhSoU-v7n7Xvyn7ovznMXN_RnOfyVbLKLe6sGX6B-ieHzA_vABPAwKaB-KFeOdMpd9HfIGGJFt1ExnzZ803_rxwT_u8s)

1. Select which part should become the parent component (i.e. the part you will be making) and click **Replace**.
  1. Once you confirm, the assembly structure will be deleted and replaced by a manufactured part. Any parts that you do not select will become children of your selection.
  2. Only manufactured components can be assigned as the new parent part. If you don't see the part you want to select listed as an available option, confirm that it is not a purchased component before proceeding.

![](https://lh4.googleusercontent.com/IPSKn5bcnqJ_vgE5glIKVjIcHvVg2lxccsJ0EKzj2rmF5-I6VGiUhpF4n-iNxzTI1V9Fb6E_1_s1RB2EnZsqOfkFi60XjbPZqXDtpH6AsVDZwJU_2AII8OP5dVv0EyNoywwGy8gukp3gsbNlxs72c-g)

1. To view the hardware in this new structure, use the navigation bar or navigate to the Components section of the new parent part.

![](https://lh4.googleusercontent.com/EnWEyDia0Unor48ClpgOia4T5Fpfw2FU7NAP3i3OVjcn66k80yB4d2JlAHX5AdE4zRzrKGaBch4gM_NagOuGhHYy6Bwf_u0pfBh5KXZXo9UltWwQrl-vC0AVQFa0oI0k6Qa8Q0aholcaMbOGSmA3b4Q)

*Note*: This action is also available for subassemblies. To convert a subassembly, click the three buttons next to the subassembly in the Assembly components section and select **Replace assembly with manufactured component**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6418738150f28e43c4c5c43d/file-1r3uNYHXra.png)

## Assign purchased components

Next, cost each piece of hardware in the quote item by assigning it to an entry in your [purchased component library](https://help.paperlessparts.com/s/article/purchased-components#h.xxur1ljdyucb).

From the components section, click the three dots next to the part and select **Convert to purchased component.**

![](https://lh4.googleusercontent.com/xVIvQgqQyR_Ob3_J_gEpMMtr9XjtJtMgebvDBD5CK_3CMjUGr6_HPnYqpYJydkE1nvlbYTFiUiJAbOkcHtmRO4cElqUzH9yMllbUHXJjwzHge83OQ2jVPIJMpztKlGJJJevV28QUHeqSyiw5ezedkAE)

From there, follow the instructions [here](https://help.paperlessparts.com/s/article/purchased-components#h.xxur1ljdyucb) to link the part to an entry in your purchased component library.

Once you've assigned all purchased components, you can now complete the quote just as you would any other single-component part!
