---
title: "Similar parts search (BETA)"
slug: similar-parts-search-beta
source: https://help.paperlessparts.com/s/article/similar-parts-search-beta
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Similar parts search (BETA)

> Source: https://help.paperlessparts.com/s/article/similar-parts-search-beta  
> Topic: Part Analysis & Interrogation

#### Easily find historical parts that share common features or geometry using similar parts search. [BETA]

This feature is in an extended beta. It is **not yet complete** and **not** **being actively worked on**.

We welcome feedback on this feature but do not have a timeline to make changes.

In this article:

- Faceted search
  - Video Tutorial
  - Written Walkthrough
  - Search Parameters
  - Use Cases
- Parametric Search
  - Video Tutorial
  - Written Walkthrough
  - Use Cases
- Tips and Tricks

##

##

---

## What is similar parts search?

Similar parts search is a module in the Parts Viewer that will help you and your team quickly find parts with similar geometry and features. Accessing historical data about similar parts can help you determine important costing variables quickly and consistently, like setup time and runtime. Whether you want to reference previous runtime estimates, an attached outside service quote, an actual from a job, or even just notes on a part, having something similar to work off of can speed up the quoting process and ensure consistency.

Note: If you have feedback on the interface or would like additional product training, [please use this calendly link to book 30 minutes with our team](https://calendly.com/dana-pdm/30min).

### Faceted vs. Parametric search

There are two search methods in the similar parts module: [Faceted search](#faceted-search) and [Parametric search](#parametric).

**Faceted search** uses the high-level geometric properties of a part to find similar parts. You can use this to find parts with generally similar designs, such as mirror image parts or parts of similar shape and size.

**Parametric search** looks for similar parts by feature or manufacturability warning. Parametric search can be useful when quoting a part with a feature that seems difficult to machine, such as a challenging pocket or deep hole.

---

##

## Faceted search

#### Quick start guide

1. Open the part that you're currently quoting in the Parts Viewer and click the Similar Parts button.
2. Select each relevant Search Parameter and adjust as needed. Click Search.
  1. Learn more about Search Parameters here.
3. To view a specific result, click Open in Viewer.
  1. From there, access historical notes in the Collaboration section or pricing in the Quotes tab.

#### Video tutorial

#### Written walkthrough

Faceted search uses high-level geometric properties to find similar parts, like size and volume. Use Faceted search when you want to find parts with generally similar designs, such as mirror image parts.

Let's say you're quoting a part, and you'd like to review some historical quotes to ensure consistency before assigning a specific value such as run time. First, navigate to the Part Viewer from the Build a Quote page by hovering over the part thumbnail and clicking Open Viewer.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356eb074d805871ceaa62d9/file-QKNQHCwUjX.png)

Here, you can open the Similar parts search drawer by clicking the orange gears on the right.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356eb3d9471985a5ac55142/file-oAjjbCfkyf.png)

This will open the Similar parts search drawer. Define your search parameters (such as material and dimensions) to narrow down on key results before clicking **Search**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356ec9b927a2c1634dfd436/file-v6CHnbbqmJ.gif)

The results of your search will be ranked based on how well they satisfy your search criteria - in other words, how similar they are to the part in the categories you've selected. Keep in mind that a 100% match does not necessarily mean they are the same part, but rather that they are perfectly similar in the specified categories.

If you found what you were looking for and want to use these same search conditions in the future, you can save this search by clicking **Filter Options** and selecting **Save Active Filters**. (You will need to assign the filter a name and click **Save**.)

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356ee1a9471985a5ac55159/file-4aYBIYYqj3.png)

To get more information about a specific search result, click **Open in Viewer**. From there, you can review historical notes, attachments, and even the status of historical quotes.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356eec3de258f5018eb73bf/file-x4UB2WLVOP.png)

#### Search parameters

| **Parameter** | **Match Criteria** | **Notes** |
| --- | --- | --- |
| Material | Specify whether or not to search by the exact material family assigned to the part.    e.g. "Aluminum" or part material name e.g. "Aluminum 6061-T6" | If a material is not set, selecting Material will filter for parts that also do not have a material assigned. |
| Min. Dimension | Specify how different a result's minimum dimension can be from the minimum dimension of the original part. | The minimum dimension used here comes from the optimal bounding box around the part. |
| Median dimension | Specify how different a result's median dimension can be from the median dimension of the original part. | The median dimension used here comes from the optimal bounding box around the part. |
| Max dimension | Specify how different a result's maximum dimension can be from the maximum dimension of the original part. | The maximum dimension used here comes from the optimal bounding box around the part. |
| Volume | Specify how different a result's volume can be from the original part's volume. |   |
| Area | Specify how different a result's area can be from the original part's volume. |   |
| Edge length | Specify how different a result's total edge length can be from the total edge length of the original part. | Not available for mesh file comparison (STL, 3MF, 3DPDF) |
| Mass properties | Specify how different a result's innate mass properties can be from the original part's innate mass properties | Mass properties helps describe the relative distribution of mass on the part relative to its center of gravity. Shapes with similar mass properties (excluding other parameters) will likely have similarly located balance points if you were to try to balance the object on the tip of a broom handle. |

*Note: Excluding exact matches will filter out any results that are a 100% match.*

### Use cases

##### Dimensions only

Using just the dimensional parameters (minimum, median, and maximum dimensions) will return results that are similar in size. These results may be useful for determining workholding strategies and what machines to run the part on. This can help with determining setup times. Dimensional searching is really the baseline for similar parts searching.

##### Dimensions + volume

Combining dimensions and volume can help find parts with similar volume removals, which can be useful for volumetric runtime comparisons.

##### Volume + area + edge length

Volume to surface area ratio is a common metric for describing the complexity of a design. For parts with similar ratios, they likely will have similar complexity as it pertains to part levels (easy, medium, hard). Ratio of volume to edge length can similarly be used to bucket parts by complexity. When using volume, area, and edge length together, you can even find shorter or fatter versions of parts, where using dimensional filters would exclude those from results. Using volume, area, and edge length together with one dimensional filter can help minimize the presence of false positives.

##### Using material to refine results for runtime comparison

Include the material parameter to refine results for more applicable reference points for runtime estimates. A runtime for the same geometry made out of aluminum versus titanium will be vastly different.

##### Using mass properties to refine results

Mass properties helps describe the relative distribution of mass on the part relative to its center of gravity. Shapes with similar mass properties (excluding other parameters) will likely have similarly located *balance points*if you were to try to balance the object on the tip of a broom handle. Mass properties are a great parameter to refine search results that are a bit too broad using just other categories.

##### General usage

When in doubt, start with the dimensional search. Open up the percentage differences to get more results or optionally remove the median dimension as a parameter. Once you get over a couple hundred parts with models, these parameters should yield results that you can refine further. Use parameters like mass properties, volume, area, and length to refine those results. If you are after a useful data point for a runtime estimate, include the material family as a parameter for search. If this procedure doesn't yield anything, play around with edge length, volume, and area. Start at 10% and open up parameters.

Spend some time trying different combinations and save useful filters as you find them.

---

## Parametric search

#### Quick start guide

1. Open the part that you're currently quoting in the Parts Viewer and click the Similar Parts button.
  1. Your part will need to have an interrogation assigned to it.
2. Select the feature or manufacturing warning that you want to search by. Click Search.
3. To view a specific result, click Open in Viewer.
  1. From there, access historical notes in the Collaboration section or pricing in the Quotes tab.

#### Video tutorial

#### Written walkthrough

Parametric Search allows you to search for similar parts by feature or manufacturability warning. This can be useful if you're quoting a part with a complex feature and want insight as to how you've costed it in the past.

Let's say you're quoting a part with a challenging pocket, and you want to see how you've costed pockets like these in the past - or if you have any insight as to how you actually machined them. First, navigate to the Parts Viewer from the Build a Quote page by hovering over the part thumbnail and clicking **Open Viewer**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356eb074d805871ceaa62d9/file-QKNQHCwUjX.png)

Here, you can open the Similar Parts search drawer by clicking the orange gears on the right.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356eb3d9471985a5ac55142/file-oAjjbCfkyf.png)

Select Parametric search.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356f168de258f5018eb73d5/file-CQqad7ZLfR.png)

Next, we need to select a single instance of a feature or manufacturing warning from the CAD tab - in this case, our pocket. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356f2114d805871ceaa6303/file-gdkxk4bfhT.gif)

Note that if you don't see a list of features, you likely still need to assign an interrogation to this part.

Click Search to find parts that have features similar to your selection. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356f240927a2c1634dfd45b/file-YfDuvYFvmi.png)

To get more information about a specific search result, click Open in Viewer. From there, you can review historical notes, attachments, and even the status of historical quotes.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6356f2944d805871ceaa6306/file-U0nqw8sNN1.png)

*N**ote: P**arametric search will only return results for parts that have been assigned the same interrogation as the part you're searching with.*

---

#### Use cases

##### Lathe interrogation

- Lathe stock
  - This describes the minimum bounding cylinder of the part along its turning axis. Searching for similarity on this feature will return turned parts with similar profiles.
- Lathe slender part
  - This compares the part's length along its turning axis to the minimum external feature diameter on the part. Searching for parts with similar ratios will return results with similar looking profiles that can be useful for workholding comparison.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/636045c57678db1f1186a187/file-tVtjoSHz6Z.png)**Milling interrogation**

- Searching for a similar deep hole
  - If there is a deep hole that you cannot make in your shop or you are not sure how to approach it, look for parts that have a similar looking hole
- Challenging pockets
  - If a part has a really deep pocket or a pocket with a tricky radius, search for another part with a similar one to understand how you approached it

##### Sheet metal interrogation

- Search for parts with unusual bend lengths, radii, and directions to help with setups

## Tips and tricks

- Whenever you come across a faceted search filter that gives you a good result, save it for later
- Keep track of notes on how you approached parts or arrived at runtime estimates in the internal team chat. This will allow you to reference this information quickly when looking up similar parts.
- The geometric search will reflect manual changes to geometric attributes
- Similar parts search will only work for primary files
- Faceted search will find sub-parts in an assembly
- Select all search parameters and set them to 5% or less to find revision changes
- Select min, median, and max dimensions at 1% deflection to find mirror image parts

Note: If you have feedback on the interface or would like additional product training, [please use this calendly link to book 30 minutes with our team](https://calendly.com/dana-pdm/30min).
