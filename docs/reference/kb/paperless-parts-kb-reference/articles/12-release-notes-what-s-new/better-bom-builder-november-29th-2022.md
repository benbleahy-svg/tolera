---
title: "Better BOM Builder - November 29th, 2022"
slug: better-bom-builder-november-29th-2022
source: https://help.paperlessparts.com/s/article/better-bom-builder-november-29th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Better BOM Builder - November 29th, 2022

> Source: https://help.paperlessparts.com/s/article/better-bom-builder-november-29th-2022  
> Topic: Release Notes (What's New)

This fall, our team shipped the Better BOM Builder series - a set of six critical enhancements to the assembly quoting process in Paperless Parts. The six releases included:

1. [Flexible BOM editing](#flex-BOM)
2. [Manufactured parts with hardware](#MCwC)
3. [Replace referenced part with new version](#replace-ref)
4. [Convert subassembly to purchased component](#convert-sub)
5. [Upload child component with CAD breakout](#upload-CAD)
6. [Replace assembly w/ manufactured component](#replace-assem)

Now that the entire series is live, we want to ensure that all Paperless users who quote assemblies fully leverage the Better BOM Builder toolkit. This document includes info on why we built each feature and how to use it. If you'd like to follow up with a member of our team, reach out to our Support team - either by emailing [support@paperlessparts.com](mailto:mailto:support@paperlessparts.com) or through the Help beacon.

For a refresher on our approach to assemblies, as well as a guide to some of the language we will use throughout this document, check out our [Intro to Assemblies article](https://help.paperlessparts.com/s/article/assemblies-data-types-and-terminology).

---

## Flexible BOM editing

Before this release, users were not able to edit the CAD-extracted tree of any assemblies in Paperless. A component's quantity and location in the tree were both locked, and in order to make any adjustment to the BOM, you would need to fix the part in CAD software and re-upload it into Paperless.

Now, you can edit the CAD-extracted quantity of components as well as move them up or down in the tree structure without having to leave Paperless - or even your quote!

- How do I change the CAD-extracted quantity of an assembly component?
- How do I move a component down a BOM level?
- How do I move a component up a BOM level?

*Note*: To make any changes to a CAD-extracted BOM, you will need to be in the **Child BOM** view. **Child BOM** view will only show components and subassemblies at the level of the assembly you are currently in. **Flat BOM** view will show all components and subassemblies across the entire assembly. You can change your assembly view by toggling between **Flat** and **Child BOM** in the **Assembly Components** section.

![](https://lh3.googleusercontent.com/CMWU8GK-wEZWkHpszpipYSE9gVHU-KXUBZYDN0PV-z5QKnhn1nn5ACRwH2_I8VGWzM1cwRQaRp9fng0PsY1xBcPpof8AS7moJcT9sqcWZTwT6XFajM7T3hcEqdvcJFNiRuoqn5J_HsoEoNxp3ecR1Ra6E8NS6lDNXpR2DU-NEuPQLHRxo8hcp4nd5ChVGA)

#### How do I change the CAD-extracted quantity of an assembly component?

1. Navigate to the **Assembly Components** section of the quote item.
2. Make sure that you are in **Child BOM** view.
3. To change a component quantity, click the blue number in the **Node Qty** column and type the new desired quantity. Press ENTER to confirm.
  1. Keep in mind that you will be changing the quantity of the component at the specific level you are in. If you are *not* in a subassembly, this will be the number of components per assembly. If you *are* within a subassembly, this will be the number of components per subassembly, and the total number of components per assembly will be multiplied by the number of subassemblies per assembly.

####

![](https://lh5.googleusercontent.com/bzb_T2nb5JRf95rGL4Iu_Fp8xD1xDjVoLFwqjh4Y8SzuFlFEMMMAOlR9faGtG2aPAWnjlUTU2dycWIrD5Q9v0kv_Ob-v0BqVKnMaBmWnW6F9tdjcLKZG2stOv__YhikqLETietjci8ssdy0dps5aJF4sDnpEQwtAHvyVQ7YLEm6o1qun-VRdgGjPQ25c2Q)

#### How do I move a component down a BOM level?

1. Navigate to the **Assembly Components** section of the quote item.
2. Make sure that you are in **Child BOM** view.
3. Click the three dots next to the component that you want to move.
4. Select Move down a BOM level. This will open the **BOM restructuring** drawer.

![](https://lh3.googleusercontent.com/u4kVjjIrSHr2R0TSO44jiyeOFJA2m2S1mwfM0y_tPEwglWK8QgSwG8sNAjGHshIRnDx4rH9BTY8DdHIUJRTayj3GWGHwfHz-Cm_gGNSNQjTNsjbzAvypY4QBZr8bd9Mj9U9dwKjqe-y4FDrm7xf1As07dzH27t26y1crwJWk6DHGuLR3fJ6DcTHgn6UXsg)

1. Select the subassembly that you want to move the component underneath.
2. Use the **Current level** and **Lower level** fields to assign how many components should be at each level after you move.
  1. Ex. If there are two instances of this component in the assembly and you only want to move one of them down a level, type "1" in **Lower level** and "1" in **Current level**. To learn more about using these fields, check out [this article](https://help.paperlessparts.com/s/article/editing-the-cad-extracted-bom).

1. Click **Confirm** to move the component(s).

![](https://lh3.googleusercontent.com/ETRO-mEo-8ZN_YRCwmwjmg0qAk3IZFGq03xAmtC8_DAnyGcgkGzIF6qBzytd7fmblkU0zFXYQ7XiX63GExDtiyAD44MHVNnY-pmblGET0b6tdBZ-tXjP-mIyWtGx_-J2x1j5nzPFkWbgPkOhj5hKli0UABY52NY4oLA_j5hurLHe1w7mnEVG-hrxkJU8zw)

1. Confirm the new structure is correct by checking the tree in the navigation bar.

![](https://lh4.googleusercontent.com/uIFsZNPcHqMAn6RMpqiHZ4fysiEhY7WirfhavJovddvne-svAH-MXLZa8SkOk1x-hfasrZglttazipYqpU46X3rnytjzLMFYt4YFdwqpdXHzHzDSBRD3WscbmZ3SNObW6x2e5APwvIS_5lWV-0C9YCiibJ0GY-pz6GsWzBrs9n47HSgxARyTtEu_OflIlg)

#### How do I move a component up a BOM level?

1. Navigate to the **Assembly Components** section of the quote item.
2. Make sure that you are in **Child BOM** view.
3. Click the three dots next to the component that you want to move.
4. Select Move up a BOM level. This will open the BOM restructuring drawer.

![](https://lh5.googleusercontent.com/3ZkPLMQV5vhDL_alVtqAe7MSUCNe4QcMNiNEeVKEeTa1Ce8hHR5utyb6QZPtXju31Wac7zOULQ7XmygaYYHGt9RWnes8iiQuYZMyh_YEPYUQKnJ3Eeu4iIEdEWUSG_FHafBsSe35s7IelUzLH1xih0AcjbbYSKIF41rUN0jgx8lH-jhI4aWzEvEaAYhWvQ)

1. Use the Current level and Upper level fields to assign how many components should be at each level after you move.
  1. Ex. If there are two instances of this component in the assembly and you only want to move one of them down a level, type "1" in Lower level and "1" in Current level. To learn more about using these fields, check out this article.

1. Click Confirm to move the component(s).

![](https://lh3.googleusercontent.com/0gPkoPIr649YIIcAO2hvnTPkDHciqacf8HgOAoBnYULOuJXQ30RxslG61BGinSX1Kb1YINtXbdsRwf_zxXMPDBX-6trM5TOJY9uPUxfm9HsnpLieRH35BjFrs4cXFrYKpwtMvQn9qHv3wWx9Fl1OCA2TK8f0Pn-TVO37rKWK6lE_wsH6c1yStn7z9zcQDA)

1. Confirm the new structure is correct by checking the tree in the navigation bar.

*Note*: If you are moving a top-level component up a BOM level, this will move the component out of the assembly and create a new quote item.

---

## Manufactured parts with hardware

Although Paperless can extract the component quantities and structure of an assembly from a CAD file, we are not able to automatically distinguish which parts are manufactured components and which are hardware. Because of this, a model with more than one component will come into Paperless as an assembly even if it is actually a single-component part with hardware. This creates an additional assembly part number and does not align with how users typically quote parts with hardware.

In this release, we added a **Components** section to quote items. This section will contain a part's associated hardware even if the part is not an assembly, allowing users to quote parts with hardware *without* creating an additional assembly part number.

There are two ways to set up a part with hardware in Paperless Parts.

#### Adding hardware to a part

If you're quoting from a PDF or a CAD file that does not include hardware, you will likely need to add hardware directly to an existing single-component part after creating your quote item.

1. Navigate to the **Components** section.
2. Click **Add components to top level** and select **Add purchased component**.

- This will open the Purchased Components drawer, where you can either select an existing inventory item or create a new entry in your Purchased Components library. Use the **Node quantity** field to adjust how many pieces of hardware you're adding per part.
  1. To learn more about using your purchased component library, check out our Purchased Components Overview.

- Once you've made a selection, click **Add component**.
  1. The drawer will remain open, so you can add as many components as needed before closing it.

- If you need to account for any hardware-related cost other than piece price (such as time per insert), add it to the part as an operation.

- This will open the Purchased Components drawer, where you can either select an existing inventory item or create a new entry in your Purchased Components library.
  1. To learn more about using your purchased component library, check out our Purchased Components Overview.
- After finalizing your selection, click **Convert**. The subassembly will be removed from the tree and replaced by a purchased component.
