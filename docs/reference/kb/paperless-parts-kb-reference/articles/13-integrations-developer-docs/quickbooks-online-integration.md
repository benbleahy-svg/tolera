---
title: "Quickbooks Online Integration"
slug: quickbooks-online-integration
source: https://help.paperlessparts.com/s/article/quickbooks-online-integration
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Quickbooks Online Integration

> Source: https://help.paperlessparts.com/s/article/quickbooks-online-integration  
> Topic: Integrations & Developer Docs

## How It Works

The QuickBooks integration will create invoices in Paperless Parts in two scenarios:

1. For orders won via Credit Card - Invoice is created when order is placed.
2. For orders won via Purchase Order - Invoice is created when parts are marked as shipped through the Paperless Parts Platform.

This reduces the manual data entry you do to enter data from Paperless into QuickBooks.

In the QuickBooks invoice, the memo field is used to track the Paperless quote and order number that the invoice corresponds to. We also include a URL directly to the order.

---

## Connecting to QuickBooks

1. Click on your name in the top right corner of your screen, and then select Settings from the dropdown.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/61b0dbfc7a3b8c03913d5250/file-V8dA1YZSdP.png)

Settings will appear on the left side of your screen. Within this navigation, look for Integrations, and then click on QuickBooks (Beta), or [click this link](https://app.paperlessparts.com/settings/integrations/quickbooks) while logged in.![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ab8ddefc78d0553e548a8/file-4EiKd2Aqe4.png)

2. You will see a page that shows the status of your QuickBooks Integration. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ab95f0332cb5b9e9b8a3a/file-BC7FU7HbfY.png)

3. Click on the "Connect" button. If you are not logged into QuickBooks, you will be prompted to log in. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ab9b70332cb5b9e9b8a3c/file-T0nBVdtSTZ.png)

4. After logging in, you will be prompted to connect your QuickBooks with Paperless Parts. ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617aba579ccf62287e5f0c53/file-peAqTyusOT.png)

5. Once ready, your QuickBooks page will look like this in Paperless:
![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ac22befc78d0553e548e6/file-Gy9Ct7Q25y.png)

Now your Paperless Parts account will push invoices into QuickBooks.

---

## How Your Paperless Invoices Appear in QuickBooks

#### How Credit Card Orders Appear in QuickBooks

When a credit card order is made on Paperless Parts, an invoice will be created in QuickBooks. The customer for the invoice will be addressed to Paperless Parts.
![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ac4202b380503dfdff4be/file-B2ZkhKWBJ2.png)

Opening the invoice will show the line items in the quote, the shipping fees, and the credit card and service fees.

---

## How Purchase Orders on Paperless Appear in QuickBooks

##

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ac5aaefc78d0553e54909/file-xKTCiSfZe9.png)

Invoices for Purchase Orders appear after you ship parts in Paperless Parts.

#### Shipping Parts in Paperless

To see an invoice created for a PO, you need to mark parts as shipped in Paperless.

1. Start by going into the order in Paperless Parts.

2. Ship the parts from the order by clicking on the "Ship Parts + Bill Customer" button
![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ac6530332cb5b9e9b8aa2/file-QsyGkJpMvK.png)

3. Enter the quantities you are shipping and confirm the shipment.

4. After confirmation, the invoice will appear in QuickBooks.

---

## Tips on Viewing Invoices in QuickBooks

We suggest turning on the "Memo" column to see your order details when viewing invoices in QuickBooks.

1. Navigate to your Sales.
2. From the All Sales screen, we suggest enabling the column for "Memo".

This exposes the memo field. Paperless uses this field in order to add the Paperless Quote and Order Numbers as well as a link directly to the quote.

Please ensure the Paperless quote/order's contact has an account, and that you have selected either PO or CC as the payment option when facilitating an order.

---

## How Do We Handle Taxes?

If you are taxing your customers in Paperless, we will reflect the tax in QuickBooks. *Note that orders with an account set as "Tax Exempt" in Paperless will **fail** to export into QuickBooks, since in QuickBooks accounts must have a reason for being tax-exempt, which we do not have a field for in Paperless (see QuickBooks documentation [here](https://quickbooks.intuit.com/learn-support/en-us/help-article/manage-customers/add-manage-customers-quickbooks-online/L0M9mMZmd_US_en_US), at 1:16 in the video).*

In the following example, you will see that both the part and the shipping are taxed. This is because this supplier is based in Ohio where taxes apply to both the sale item and shipping.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/617ac6ea0332cb5b9e9b8aa8/file-wwqAc2San0.png)

The tax percentage is 10% just like how it is specified in Paperless for that customer.

---

## How to handle Canceled Credit Card Orders

At the moment, when you cancel orders in Paperless, you will have to void the invoice manually in QuickBooks.

Additionally, we do not handle cancellation of credit card orders that have partially shipped.

#### **Explore Settings:**

- User Profile
- Company Settings
- QuickBooks Online Integration
- Accounting Updated
- Smart RFQ Settings
- Digital Quote Settings Updated
