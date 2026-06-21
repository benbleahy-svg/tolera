---
title: "Quote actions"
slug: quote-actions
source: https://help.paperlessparts.com/s/article/quote-actions
topic: "Quoting Workflow (Build a Quote)"
captured: 2026-06-19
---

# Quote actions

> Source: https://help.paperlessparts.com/s/article/quote-actions  
> Topic: Quoting Workflow (Build a Quote)

Use the **Actions**menu in the Build-a-Quote page to change a quote's status or perform costing actions across quote items.

#### On this page

- Index of available quote actions
- FAQ
  - When should I download a quote as a CSV vs. an Excel file?
  - When should I use Create revision vs. Copy?
  - Why are some actions in the menu unavailable?
    - Why can't I download my draft quote as a PDF?

---

# Available quote actions

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64356ef14b12852670452cd0/file-eunqlms31Y.png)

#### Next steps

- Facilitate order: Change the quote status to "Accepted" and create an order from the quote.
  - Note: Depending on your organization's checkout settings, this may send a confirmation email to your buyer.
  - Note: If you have an integration with an ERP system, facilitating an order will likely create a new record in your ERP.

#### Download

- Files (structured): Download all files in the quote locally into a structured folder, with subfolders for each quote item category and line item.
- Files (flat): Download all files in the quote locally into one flat folder (no subfolders).
- PDF: Download a PDF version of the quote.
  - Note: This action is only available for quotes that have already been marked as sent or ordered. Why?
- CSV: Download a .csv file with high-level information about each quote item, including its part number, price, and dynamic lead time options.
- Excel: Download an .xlsx file with detailed costing and pricing info about each quote item.
  - Learn more about the standard Excel export here.

#### Quote

- Multi-component nesting: Open the multi-component nesting module, where you can create a nest across multiple sheet metal or linear metal parts in a quote.
- Copy: Create a duplicate of this quote with an entirely new quote number.
  - Note: The new quote will link back to the original quote it was copied from.
- Create revision: Create an exact duplicate of the quote with a revision number.
  - Note: Creating a revision of any quote in draft will cause the original quote to expire.
  - Note: Select View revisions from the Build-a-quote page to see a quote's revision history.
- Resend: Resend the quote to your contact.
  - Note: This action is only available for quotes that have already been marked as sent or ordered.
- Mark as sent: Change the status of the quote to "Outstanding". This will "lock" the existing version of the quote and prevent further changes.
- Mark as lost: Change the status of the quote to "Lost".
  - Note: Tracking which quotes you've lost can be important to maintain accurate analytics on your buyers and your shop's performance.
- Cancel: Void the digital quote you sent to your buyer and change the status of the quote to "Cancelled".

#### Delete quote

Deleting a quote will move it to the trash tab of your Quotes dashboard.

# FAQ

## When should I download a quote as a CSV vs. an Excel file?

Each option is useful for different circumstances. The CSV file provides high-level information about the quote you offered your buyer, including the price of each quote item, some quote item-level information, and lead time options. The Excel file has two tabs that provide a detailed breakdown of the operations applied to each quote item (including setup and run time), making it more useful for tasks like resource planning.

Learn more about the Excel file export [here](https://help.paperlessparts.com/s/article/standard-quote-exporter-march-1st-2023).

## When should I use Create revision vs. Copy?

Both of these actions will create an exact copy of the quote you're currently working on. However, copying a quote will create an entirely independent duplicate of the quote, while creating a revision will impact the revision history and status of the original quote.

For instance, let's say you're working on Quote #3000, which is currently in draft. Your account currently has existing quotes up to #3005.

If you create a **revision** of #3000, a duplicated quote (#3000-1) will appear in your drafted quotes. Quote #3000 will be moved to expired, but you can still view it from #3000-1's revision history.

If you create a **copy** of #3000, a duplicated quote will appear in your drafted quotes as quote #3006 (since 3006 is the next available quote number in your account). It will clearly state that #3006 is copied from #3000, but quote #3000 will not be impacted and there will be no visible revision history.

## Why are some actions in the menu unavailable?

Some actions are dependent on a quote's status. For instance, the Resend action will not be available for quotes that haven't already been finalized, marked as sent, or turned into an order.

You can confirm a quote's status by checking the badge underneath the quote number in the Build-a-quote page. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64396257ad20e8714a50d7e2/file-blIV67HugO.png)![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/64396265ad20e8714a50d7e3/file-DWKN2tSKX5.png)

### Why can't I download my draft quote as a PDF?

Once you finalize a quote or mark it as sent, that version of the quote will be frozen to preserve the record of what was sent to your buyer. Because downloading a PDF version of the quote will allow you (or a member of your team) to send it to a buyer outside of Paperless Parts, you're required to mark it as sent first to freeze that version of the quote and maintain that system of record.
