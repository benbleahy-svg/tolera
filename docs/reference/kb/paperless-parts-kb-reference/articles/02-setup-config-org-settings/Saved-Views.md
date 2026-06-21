---
title: "Saved Views"
slug: Saved-Views
source: https://help.paperlessparts.com/s/article/Saved-Views
topic: "Setup, Config & Org Settings"
captured: 2026-06-19
---

# Saved Views

> Source: https://help.paperlessparts.com/s/article/Saved-Views  
> Topic: Setup, Config & Org Settings

Customize the quotes and parts you see on the Quotes page and narrow down on what's important with Saved Views.

### On this page

- Creating new Saved Views
- Sharing Saved Views
- Saved View examples and inspiration

# Creating a new Saved View

 To create a new View, click the + symbol next to Quotes or Line Items in the left-hand navigation bar.This will open a window where you can assign the View a name, mark whether or not it should be your default View, define share settings, and customize your filters and column selections, as well as the order of columns and results. By default, your account will have 10 Saved Views, including:

- My quotes (private)
- Unassigned quotes
- Quotes in draft
- Quotes due this week
- Overdue quotes
- Outstanding quotes
- My line items (private)
- My line items due this week (private)
- Unassigned line items
- Line items in draft

 You can edit, duplicate, or delete any existing Saved View by clicking the three dots next to the View to open the action menu.You can also export a view or share it with your team, either by sending a team member a view's URL or by downloading the view as a CSV (available from the actions menu above). Let’s walk through an example of setting up a Saved View.If you’re a salesperson and want to see all of the parts that your team has quoted for a strategic account, create a new View and set the following:

- View by Line Items
- Choose if this View should be private or public
- Order by Created on: Latest -> Earliest (will show you the most recent parts first)
- Filter by the strategic Account
- Choose all relevant columns to display and drag and drop to reorder them (ex. Part number, description, quote status, status, workflow steps, price)
- Click Create View

# Sharing Saved Views

 Saved Views have two visibility options - Team and Private - but there are times in a shop where it can be valuable to share a Saved View among a small group of people on your team. If your management team has a weekly review of active quotes, or you have multiple purchasers going out for vendor quotes, you may need to share the results of a Saved View with a teammate, or even set up the same private view for multiple users. The best way to share a Saved View is by sending its unique URL. For example, let's say you're an estimating manager, and you want to help your team set up Saved Views to see how many parts they have due each day. Creating a Team view won't work in this case as you'll need to filter by a different estimator for each team member.Start by configuring a private Saved View with the following:

- View by line items, order results by "Due on: Earliest -> Latest", and apply the following filters:
  - Quote status is draft
  - Date due is today
  - Estimator is [Estimator]
  - Line item status is Not Started or In Progress
- We'll prioritize the columns Part Number, Part Description, Quote Number, Line Item Status, Account, Process, Material, and Due On by dragging them to the top of the list. All others can be hidden by deselecting their checkboxes.

Click "Create View" and send the URL to the teammate you want to share the view with. When they click the URL, they'll be brought to the view and prompted to add it to their own Quotes page. Clicking "Save to my views" will duplicate the view and add it to the recipient's Quotes page as a private View.

# Examples and Inspiration

 Because Saved Views are so flexible and configurable, it’s not always obvious at first glance what you can do with them; which questions you can answer, or which problems you can solve for your team. Below is a list of Saved Views that we believe are highly valuable, organized by who in your shop they may benefit the most.

## Estimator

### *What are the most important parts I need to be quoting?*

 Make sure a long turnaround time doesn’t hurt your chances for high-priority quote packages.

- Create a line item view and filter by estimator to only see line items you are assigned to.
- From there, filter for high priority line items, line items requested by important accounts, or line items that are approaching their due date.
- Order by due date (earliest to latest) to see the line items that are due soonest, or by priority to see the most important line items at the top.

### *What are the parts I’ve previously quoted for this customer?*

 View parts organized by account/contact by creating a line item view for your most important customers.

- Create a line item view and filter by account.
- Order by created on (latest to earliest) to see the most recent parts at the top.

### *What other parts in this part family have I quoted before? (Requires that part number indicates a part’s family)*

 This one’s not a saved view, but it is an easy way to identify parts that fall into the same family. Because this requires that parts share a common section (prefix or suffix) of their part number, it is most likely useful for aerospace shops.

- Create a line item view, likely filter by account if helpful
- Search for part prefix

## Estimating manager/Owner

### *Which parts are waiting for my review?*

 Don’t be the blocker on parts that your team has already quoted! Keep a running list of work you need to review by filtering on custom workflow steps.

- Create a line item view
- Filter by custom workflow step (workflow step before review is “complete”, review is “not started”)

### *Which parts/quotes do I need to assign to an estimator? What work currently doesn’t have an owner?*

 Make sure work doesn’t fall through the cracks by quickly assigning a member of the team ownership of parts/quotes as they come in.

- Create a quote or line item view
- Filter by estimator is “Unassigned”

### *How are each of my facilities doing?*

 Most useful for consolidated multi-site user groups (one user group with many facilities). This View is only available if your team has more than 1 facility available.

- Create a quote or line item view
- Filter by facility

## Purchasing

Which parts are waiting for a (specific outside service or material) quote?

- Create a line item view
- Either:
  - Filter by “Has operation” (outside services op) and “Quote status” “draft”
  - Filter by custom workflow step (ex. “Outside service quote” is “on hold”)

## Salesperson

### *What quotes do I need to follow up with my buyers on?*

 Make it easier to identify outstanding quotes that your buyer may have missed so you know when to reach out.

- Create a quote view
- Filter for “Quote status” is “Outstanding” and “Date last viewed” is “Never”
- Extra: Filter for “Date sent is before this week” for long-outstanding quotes
