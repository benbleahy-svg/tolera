---
title: "Add an existing part in your library to an assembly BOM"
slug: add-an-existing-part-in-your-library-to-an-assembly-bom
source: https://help.paperlessparts.com/s/article/add-an-existing-part-in-your-library-to-an-assembly-bom
topic: "Assemblies & BOM"
captured: 2026-06-19
---

# Add an existing part in your library to an assembly BOM

> Source: https://help.paperlessparts.com/s/article/add-an-existing-part-in-your-library-to-an-assembly-bom  
> Topic: Assemblies & BOM

If you're quoting an assembly part that includes a subassembly or manufactured child part that you've quoted before, you can use the **Import historical work**option to import the existing part (and its costing) from your library to the new assembly.

First, add the new assembly part to your quote [as a new quote item](https://help.paperlessparts.com/s/article/setting-up-quote-items#h.y0w06dog8ooi). Make sure that the part number and files represent the entire assembly part that you'll be quoting for your buyer.

Next, add the existing child part to the quote by adding a new quote item and [select Import historical work](https://help.paperlessparts.com/s/article/setting-up-quote-items#h.odvegu4tql80). Search for the existing part in your library.

*Note:*You'll likely want to toggle on the **Include child parts**option - otherwise, your search will only return top-level assembly parts, not subassemblies or child manufactured parts.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642493a44cd1ab01bbe8b08e/file-iNp4xvPw9Y.png)

Once you find the existing part in your library, select it and click **Import item**to add it to the quote. This will import the part as a new quote item.

Click the three dots next to the imported child part and select **Replace referenced part with new version.** This "disconnects" the version of the child part in this new quote from versions of the part in other quotes, so making changes to the part's structure here (such as part number) won't affect any other quotes that this part is present in.

![image.png](https://d33v4339jhl8k0.cloudfront.net/inline/89310/3a0e7d33585c52bccb3d993e94940656a4edc2b4/227ccc543dd137f2324dc32cc665699e5027e80b/image.png)Select both quote items, click **Actions**, and select **Merge quote items into assembly**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642497e6a3236b1edbce8a04/file-R0KC5WSj1D.png)Select which part should become the top-level quote item (the quote item that represents the entire assembly part).

**Do not select regenerate operations!** This will delete any costing that already exists on the child part you imported from your library.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/642498ac7bf4bb61c01166c3/file-HWHYC3caVc.png)Click **Merge** to confirm. The two quote items will become one and you can view the imported part in the **Components**section of the quote item.

From there, update the quantities, [costing](https://help.paperlessparts.com/s/article/costing-a-part), and [pricing](https://help.paperlessparts.com/s/article/pricing-a-part) as needed before sending your quote!
