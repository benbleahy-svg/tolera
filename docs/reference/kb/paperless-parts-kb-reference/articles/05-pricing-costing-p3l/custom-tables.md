---
title: "Custom tables"
slug: custom-tables
source: https://help.paperlessparts.com/s/article/custom-tables
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# Custom tables

> Source: https://help.paperlessparts.com/s/article/custom-tables  
> Topic: Pricing, Costing & P3L

Custom tables are collections of data in your account that pricing formulas (P3L) can reference. For example, one common use case for custom tables is to store material pricing. Operations can then reference that table to calculate a cost based on the specific material and geometric properties of a part.

#### On this page

- [Formatting custom table files](#h.cf1wskr1su7)
  - [Config files](#h.q3n0lb5fktce)
  - [Data files](#h.gr20453cqdu7)
- [Creating a new custom table](#h.m9x4x06e5q8h)
  - [Workcenter table example](#h.vu8etcwfk9ar)
- [Updating an existing table](#h.5iwskpi2zyja)
  - [Updating data](#h.u4ym4rvlypxp)
  - [Updating table configuration (column names, structure, etc.)](#h.wve5u2pv7pzn)
- [Best practices](#h.njfukj4zs4mn)

---

# Formatting custom table files

Each custom table in Paperless Parts is dictated by two separate .csv files:

1. **Data File**
  1. This file contains the data you would like to upload to Paperless Parts.
2. **Config File**
  1. This file dictates how to read and interpret the data file. It includes the title of each column and the type of data it contains.

In order to have a custom table appear as intended in Paperless Parts, you'll need to follow a few simple formatting rules for the config and data files.

## Config files

Config files must have the following 3 columns in this order:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63bc6efae0d50f555584051c/file-WOxrVC6Ok0.png)

- column_name
  - The name of the corresponding column in the data file.
- value_type
  - The type of data included in said column (numeric, string, or boolean).
- is_for_unique_key
  - Indicates whether the values in this column have to be unique.
    - *Note*: This column is not required to create a custom table. If you upload a config file with only column_name and value_type, the is_for_unique_key will default to FALSE for all values.

## Data files

- This file should be identical to the custom table that you expect to appear in Paperless Parts (see the [Workcenter table example](#h.vu8etcwfk9ar) below).
- Make sure each column name in the data file corresponds to a column_name in the config file.
  - Ex: If there is a "workcenter" column in the data file, there must be a "workcenter" row in the config file.

---

# Creating a new custom table

## Workcenter table example

Let's say you want to import the following custom table of workcenter data into Paperless Parts.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63bc6f5fe0d50f555584051d/file-g0KrKN3vpP.png)

The table itself will serve as the **data file.**In order to format it correctly in Paperless, create the corresponding config file.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63bc6f76a4d23862de16a684/file-26BRw5jRoP.png)

- Each column in the data table corresponds to a row in the config table dictating the column name, the type of data stored in the column, and whether or not the values in that field need to be unique.
- For instance, the workcenter row has a string type because it will include text and is marked as TRUE because there should not be two separate rates for any specific workcenter.

*Note*: For organizational purposes, we suggest that you add "-data" and "-config" to the name of each file while saving. For example:

- workcenter-data.csv
- workcenter-config.csv

Now that you've formatted your data and config files, upload them into your account from the **Configure** tab.

1. Navigate to the **Configure** tab.
2. Select **Tables** to view your account's custom tables.
3. Click **+ New Custom Table** at the bottom of the page.

![](https://lh4.googleusercontent.com/26ivJTlUsr2cE40hfeWZWcxRkJ6ir6KdvBXSsgycrEwGIJ7qK29KYXh6_vN1GzAFwSxkvlxQClCAGAmO2tuhP673FKkf9g4szJfkOzT1vWX_YrEK94i8hRbWePd5T5_BRO6t7S2flOawZGz52lnlh5tgL5kpwJ_87atxcQCtl7xAlM3LYWIPwJaTj5CYhA)

1. Create a custom table name.
  1. Note: There cannot be spaces in the table name, use an underscore.
    1. If you would like a table to be called "workcenter rates", make the table name "workcenter_rates".
  2. This table name is what you will reference when performing a table lookup in P3L, so make sure it's intuitive and easy to recall.
2. Select the new custom table you have created to open it.
3. Click **Actions**.
4. Select **Update Table**.
  1. This will open the **Update Table** panel.

![](https://lh6.googleusercontent.com/A4g5gHSyeJI9XbMTqvYW46U55sKf-Udgf7Lc6ClTDRuAZes-SQ47e3xfwXK6Y40sGktmhCctKUSSYj5nrEjKgWPS355voTyWSqPFf4lKSvbccrdrWd-vfNJpskrAyVTq6NDKwvwrTJU80jpduOHP59mfYGcJwgsSNtzJganQhDDmWFOyhXAG_GO8XLqQpg)

1. Upload the Config CSV to the **Upload Config CSV** section.
2. Upload the Data CSV to the **Upload Data CSV** section.

![](https://lh6.googleusercontent.com/uXXit0VQJDhWFPlUBb1RStMY_O5d85DUsgeok_jFb0eG4FVfNO7SR73fm6V8bL6JrDSELNFGApVw1452ZND6B0OlRnXzsOqcbyaXAqddNtZ_ao0QRP-hTwMO2gcTF1hJCjMEPXI3M9nsAaQ1VOlEEcQ63oxVHXQd9PJG5xfgME-JaPSMXr8YbHnyF1Ylug)

1. Click **Update**.

The final product will look like this:

![](https://lh6.googleusercontent.com/We9mce63BbS4OmFOggXy8jOUnuFj8FbIo0_CYBUfZzNebprRz1F3PaBAa0XEFMlhZYysu-jRsNnZrMQ2Aqm-cMkeM_jdDNS58xzzC_0tNvTg7uBDR3_DExIIKxc7X_i0T6_PsQvDReCyxEnaJkaVKmX97voE4MByAeGQ6LFwY_gH-bimuzgs8t7lQC6fcQ)

#

---

# Updating an existing table

## Video walkthrough

## Updating table data

Note: Updating a data table does NOT update column names or structure.

1. Navigate to the custom table you would like to update.
2. Click **Actions**.
3. Select **Download Data****.**
  1. This will download a .csv file with all data in the custom table.
  2. Note: Opening the file in Numbers will remove any leading zeros (this can be important, especially if you're downloading zipcodes). Google Sheets does this as well, unless you uncheck the **Convert** option when importing.
4. Modify the data and save changes.
5. Click **Actions**.
6. Select **Update Table**.

![](https://lh6.googleusercontent.com/A4g5gHSyeJI9XbMTqvYW46U55sKf-Udgf7Lc6ClTDRuAZes-SQ47e3xfwXK6Y40sGktmhCctKUSSYj5nrEjKgWPS355voTyWSqPFf4lKSvbccrdrWd-vfNJpskrAyVTq6NDKwvwrTJU80jpduOHP59mfYGcJwgsSNtzJganQhDDmWFOyhXAG_GO8XLqQpg)

1. Upload the updated data table to the **Upload Data CSV** section.

## Updating table configuration (column names, structure, etc.)

1. Navigate to the custom table you would like to update.
2. Click **Actions**.
3. Select **Download Config** and **Download Data**.
  1. This will download both the config and data files as a .csv.
4. Modify the config .csv and save changes.
  1. Note that you cannot use a number as the first character/index 0 for string-type column names. It will provide a dot operator error message notifying you of this. If the number is placed elsewhere in the string, the column name should work.
    1. Incorrect examples: "3_mm_sin_cust_cost" and "3mm_sin_cust_cost"
    2. Correct example: "sin_cust_cost_3_mm"
5. Modify the data .csv so that it aligns with the updated config .csv and save changes.
6. Click **Actions**.
7. Select **Update Table****.**

![](https://lh6.googleusercontent.com/A4g5gHSyeJI9XbMTqvYW46U55sKf-Udgf7Lc6ClTDRuAZes-SQ47e3xfwXK6Y40sGktmhCctKUSSYj5nrEjKgWPS355voTyWSqPFf4lKSvbccrdrWd-vfNJpskrAyVTq6NDKwvwrTJU80jpduOHP59mfYGcJwgsSNtzJganQhDDmWFOyhXAG_GO8XLqQpg)

1. Upload the updated config .csv to the **Upload Config CSV** section.
2. Upload the updated data .csv to the **Upload Data CSV** section.
3. Click **Update**.

---

# Best practices

- Spaces matter!
  - Extra spaces in your table's data may affect your upload or cause unintended behavior.
  - Double-check if there are extra spaces in your table by opening the CSV file in a text editor.
- Double-check the spelling in your config and data files.
  - You'll be referencing the name of the table as well as column and row names when performing a table lookup in P3L, so typos can cause unexpected results/behavior.
- All files you upload must be in .csv format.
- Check on any other operations referencing the table you're updating to ensure there are no downstream effects. It's good practice to check if you're:
  - Changing a column name.
  - Changing the P3L filters.
  - Changing an existing row.
- Updates made to custom tables or P3L will not persist to any current quote items in draft unless you **Refresh pricing** for a particular quote item.
