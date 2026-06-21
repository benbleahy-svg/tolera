---
title: "Analytics"
slug: analytics
source: https://help.paperlessparts.com/s/article/analytics
topic: "Analytics & Reporting"
captured: 2026-06-19
---

# Analytics

> Source: https://help.paperlessparts.com/s/article/analytics  
> Topic: Analytics & Reporting

# Analytics Overview

The Paperless Parts analytics tool allows you to understand your shop floor by seaming together all of the data that is captured in your process. You can quickly leverage customer information, quote data, order data, part file information, and more by breaking out numerical measurements and aggregations across pre-built groupings.

## 1. Default Dashboard

We have provided all of our users with a default dashboard containing 12 insightful queries to help you understand your shop floor. All of these queries can be filtered at a glance to tailor the data you are seeing to your needs. Additionally, our advanced analytics users will have access to 3 other dashboards by default in addition to the Paperless Parts Query Creator (Performance, Revenue, and Part Metrics dashboards). If you have questions about the capabilities of the Paperless Parts Analytics tool, or about this resource, please reach out to support@paperlessparts.com.

## 2. Editing Filters

- Date Filters - Filter Queries on your dashboard by different date ranges on the fly.
- Field Filter - Filter Queries on your dashboard by different "group by" fields on the fly.
- Edit Title - Rename your tile accordingly.

## 3. Advanced Analytics

- Part Metrics Dashboard
- Query Editor
- Creating Dashboards
- Measurements and Dimensions

---

## 1. Default Dashboard

The default analytics dashboard includes 12 tiles, each filtered to the last *x* days (exclusive of *today*). Each of these tiles can be filtered in various ways as outlined in the next segment:

1. Quotes Sent Last 30 Days - Count of Quotes sent or marked as sent in the last 30 days, represented as a bar graph by day.
2. Orders Created Last 30 Days - Count of Orders placed or facilitated in the last 30 days, represented as a bar graph by day.
3. Quotes Count Last 7 Days - Count of Quotes sent or marked as sent in the last 7 days, represented as a number.
4. Quotes Amount Last 7 Days - Sum of the dollar amount of all lines and quantities of quotes sent in the last 7 days.
5. Orders Count Last 7 Days - Count of Orders placed in the last 7 days, represented as a number.
6. Order Revenue Last 7 Days - Sum of the dollar amount of orders placed or facilitated in the last 7 days, represented as a number.
7. Customer Metrics Last 7 Days - Table representation of the number of quote items vs. order items sent to each Contact and Account as well as the Win Rate and Total Revenue for each of those Contacts and Accounts.
8. SmartRFQs Count Last 7 Days - Count of RFQ's Received through the Paperless Part's SmartRFQ Form, represented as a number.
9. SmartRFQs Quotes Sent Count Last 7 Days - Count of quotes sent in the last 7 days where the RFQ was generated from the SmartRFQ Form, represented as a number.
10. Draft-to-Send Time Smart RFQs Last 7 Days (Hours) - Turnaround time in hours from when the quote was drafted in Paperless Parts either manually, or via SmartRFQ submission, represented as a number.
11. Smart RFQs Win Rate Last 7 Days - Win Rate percentage for RFQs received via the Paperless Parts SmartRFQ form, and ordered in the last 7 days.
12. Expedite Revenue Last 7 Days - Sum of the dollar amount of Orders placed in the last 7 days where an expedite option was selected.

### Default Dashboard

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6101eb336ffe270af2a939cc/file-5Ak1QegzsH.png)

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6101e807b55c2b04bf6d920e/file-52h6LSQwxp.png)

## 2. Editing Filters

By default, queries are filtered by a date set at a fixed rolling X amount of days (exclusive of today).

### Date Filters

To edit the filter, click the filter icon and toggle the date to a fixed range, or choose a pre-defined rolling filter in the dropdown menu:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61089e9d64a230081ba1b7d1/file-c1j2CGZkdu.gif)

Let's change this to show the **rolling last 7 days**. Select your date filter, then click apply. As you can see below, the filters have been set. If you wish to save the filter, we can update the title next accordingly.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032149b55c2b04bf6d98a4/file-VOurKK0otx.png)

### Field Filters

Just like filtering by date, we can filter by different fields such as accounts. Let's filter our Quotes sent to the account Mason, Thomas, and Mcguire. Select your field filter and value(s), and click apply.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032231b37d837a3d0def26/file-XvacxHVMf5.png)As you can see, we have a bar graph of quotes sent to Mason, Thomas, and Mcguire.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/610325dab37d837a3d0def3f/file-Ad5uHlv3HT.png)

### Update Title

Now, let's update the title. Click the Menu Icon, update the title accordingly, and click save.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032584b55c2b04bf6d98ba/file-fsHv6gyNXj.png)

## 3. Advanced Analytics

The advanced analytics capability unlocks the power to create your own dashboards and queries. In this section, we will take a look at an advanced dashboard, and explore the query editor.

- Part Metrics Dashboard
  - Contents
  - Visual
- Dashboards
  - Overview
  - Creating Dashboards
- Query Editor
  - Overview
  - Creating Queries

## Part Metrics Dashboard

The Part Metrics Dashboard Includes 6 default queries:

1. Parts X Dimensions - Table view of the minimum, average, and maximum part X (bounding box dimension) of solid models uploaded to Paperless Parts, all time.
2. Parts Y Dimensions - Table view of the minimum, average, and maximum part Y (bounding box dimension) of solid models uploaded to Paperless Parts, all time.
3. Parts Z Dimensions - Table view of the minimum, average, and maximum part Z (bounding box dimension) of solid models uploaded to Paperless Parts, all time.
  - Part Dimensions can help you get an understanding of what size parts you are seeing - Look even further to see what size parts you are winning across each of your different processes
4. Parts File by Type - Spread of parts uploaded by file type. Step, Print, Vector, SolidWorks, Parasolid, and Miscellaneous. Represented as a pie chart, all time.
  - File types can help you get an understanding of where and how you are spending time quoting. Use this to help improve the percent of inbound models.
5. Assemblies Uploaded - Number of structural assemblies uploaded to Paperless Parts, all time.
6. Subassemblies Uploaded - Number of structural subassemblies within assemblies uploaded to Paperless Parts, all time.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032911766e8844fc34ba9a/file-OjRcEBBqtc.png)

### Dashboards

#### Overview

A dashboard is like a bulletin board to store different tiles/queries. Use Dashboards to organize your queries by category or by each individual on your team.

#### Creating Dashboards

Let's create our own Dashboard. Then, we will create our own query using the query editor. Click create on the dashboard toolbar next to the part metrics label, name your dashboard, and click save.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032c36b37d837a3d0def57/file-G1QhlI31T4.png)

Now that you have a new dashboard, you can copy a new query to further manipulate it. Copy the Parts By File Type query from your part metrics Dashboard to the new Dashboard you just created:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6108a0c2b37d837a3d0e003c/file-3y2Zcq90Js.gif)

Rename the copy to something different, and save it to your new Dashboard. I saved mine as a table format, rather than a pie chart:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032d0d6ffe270af2a940f5/file-vTeQGZWfyf.png)

### Query Editor

#### Overview

Now, let's further iterate on the new tile we just created. The plan will be to see our *Quote Win Rate* and *Draft to Send Time* by the file type groupings shown below. this will help understand where we are spending our time quoting.

#### Edit Query

Click edit Query to open the Query editor.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032ddcb55c2b04bf6d98db/file-TsloMSPSR1.png)

#### Adding in*Quotes Win Rate*

First, let's add a measure. A measure is a pre-aggregated column that allows you to easily build off of queries in two clicks. Add the measure of *Quotes Win Rate* "+ Measure".

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61089c2064a230081ba1b7cc/file-NsS4iZNI9E.gif)

Now we can see our win rate by file type.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61032f68b37d837a3d0def5e/file-mEg94QgQmk.png)

Now, let's add in our *Quote Average Draft to Send Time* measure so we can see how that compares across file types. Add in the measure, and then we will save this to our new dashboard.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/610897a76ffe270af2a951d1/file-J7rO6NDz3t.png)

Now, save your dashboard as a table format by clicking "Save to Dashboard":

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61089b106ffe270af2a951da/file-tqBU5PTFUg.gif)

Navigate to your dashboard and resize your tile:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6108996e766e8844fc34cbd1/Resizegif.gif)

### Measurements and Dimensions

#### Measurements, Dimensions, Segments, Time Ranges, and Field Filters -- more information can be found in the [Analytics query-builder deep dive article.](https://help.paperlessparts.com/s/article/analytics-query-builder-deep-dive)

The Query Creator is built in a fashion that eliminates the leg work of joining, aggregating and filtering your data. We can create complex and powerful queries by making use of predefined Measurements and Dimensions, and utilizing Segments Time Ranges, and Field Filters to further hone in on answers to questions you might have.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6108ad0b6ffe270af2a951fa/file-SKol2jrvJ5.gif)

| **Measurement Name** | **Description** | **Data Type** |
| --- | --- | --- |
| `Accounts Count` | Count of unique Accounts created in Paperless Parts | Number |
| `Contacts Count` | Count of unique Contacts created in Paperless Parts | Number |
| `Components Count` | Count of Unique Components existing in Paperless Parts | Number |
| `Quote Items Count` | Count of Items Quoted in Paperless Parts | Number |
| `Quote Cells Price` | Cell(s) Price of Operation(s) on a Quote in Paperless Parts | Number |
| `Order Items Count` | Count of Items Ordered in Paperless Parts | Number |
| `Orders total Price` | Total price for Order(s) in Paperless Parts | Number |

| **Dimension Name** | **Description** | **Data Type** |
| --- | --- | --- |
| `Accounts Name` | Name of an Individual Account | String |
| `Contacts Name` | Name of Contact within an Account | String |
| `Estimators Name` | Name of the team member assigned to a Quote | String |
| `Component Estimators Name` | Name of the team member assigned to a Line Item | String |
| `Team Members Date Joined` | Date your Team member signed up for Paperless Parts | String |
| `Process Name` | Name of Manufacturing Process in your Paperless Parts Account | String |
| `Operations Name` | Name of Operation in your Paperless Parts Account | String |
| `Op Defs Category` | Category of operation: *Material* or *Finish* | String |
|   |   |   |

**With these 7 Measurements and 7 Dimensions, we can create different queries.****Let's look at a couple examples.**

1. Quoted and Ordered amount by Estimator

To create this Query, add the **Dimension***Component Estimator Name*and the **Measurements***Quote items Count*, and *Order Items Coun*t:

**![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6108bfb364a230081ba1b80a/file-tFOLCMSkGw.png)**

2. Quote Items, Order Items, and Orders Total grouped by Process

To create this Query, add the **Dimension** *Process Name*and the Measurements*Quote items Count*, *Order Items Count*, and *Orders Total Price*:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6108c09c64a230081ba1b80c/file-fFo6EVNbdw.png)
