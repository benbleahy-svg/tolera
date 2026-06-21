---
title: "Order facilitation"
slug: order-facilitation
source: https://help.paperlessparts.com/s/article/order-facilitation
topic: "Orders, Checkout & Fulfillment"
captured: 2026-06-19
---

# Order facilitation

> Source: https://help.paperlessparts.com/s/article/order-facilitation  
> Topic: Orders, Checkout & Fulfillment

When your buyer places an order, it's important to mark the quote as won by creating an order in Paperless Parts. There are two ways to do so:

1. Your buyer can place an order through the digital quote using the Check out option (depending on their Account settings).
2. You or a teammate can facilitate an order from the quote in Paperless Parts.

This article will walk through manually facilitating an order from within your account. For more information on orders, including the role they play in ERP integrations, check out [our FAQ below](#faq).

# Facilitating orders

To create a new order, open the associated quote and select **Facilitate Order**.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6442cf9235387a48183972bd/file-88zlCuSzwA.png)

Select the quantities and lead times specified by your buyer. Click **Continue to shipping and payment**once you've selected all line items.

- Note: Changing the "Ships On" date for an item will adjust the lead time.

![](/servlet/rtaImage?eid=ka0Ns0000005Bu5&feoid=00N5G00000WB8Hk&refid=0EMNs00000MheqL)

If your buyer sent you a PO for a quantity not listed on the quote, click **Add adjustment**to type in the new order details.

![](/servlet/rtaImage?eid=ka0Ns0000005Bu5&feoid=00N5G00000WB8Hk&refid=0EMNs00000MhevB)

Select a payment method, ship to facility, bill to facility, shipping options, and (optionally) payment details.

![](/servlet/rtaImage?eid=ka0Ns0000005Bu5&feoid=00N5G00000WB8Hk&refid=0EMNs00000MhfEX)

Click **Review Order**to proceed. On this screen, you can view all of the items included in the order and choose whether or not to send an order confirmation email to the customer. If you typically do/don't send order confirmation emails, you can adjust this setting's default for this setting in your [checkout settings](https://app.paperlessparts.com/settings/digital_quote/checkout_settings).

![](/servlet/rtaImage?eid=ka0Ns0000005Bu5&feoid=00N5G00000WB8Hk&refid=0EMNs00000MhQsE)

Once you've finalized all details, click **Complete order.**The quote status will change to "Accepted", and a new order will be created in the Orders page.

# FAQ

## I have an ERP system for tracking orders. Why should I create orders in Paperless Parts?

If you have an ERP integration, facilitating an order is likely the trigger to push information over to your ERP.

If you do *not*have an ERP integration, the value of creating orders primarily lies in analytics. Facilitating an order from a quote is the only way to mark it as sent, meaning that you cannot have accurate win rate data without creating orders. If this is the case, you can very quickly facilitate an order once you've entered payment information by skipping shipping/billing and simply clicking **Complete order**. However, we strongly recommend entering complete and accurate information if you have an ERP integration, as some of that information may be required for the order to push over to your ERP correctly.

## I don't see "Facilitate order" in the top corner of the Build-a-Quote page.

The actions that you can perform on a quote [are dependent on its status](https://help.paperlessparts.com/s/article/quote-actions#unavailable). Although you can facilitate an order from a quote that is not Outstanding, that option is listed in [the Actions tab](https://help.paperlessparts.com/s/article/quote-actions) rather than at the top of the quote (the assumption being that Draft quotes will likely be sent before an order is placed).

*Note:*If you have a QuickBooks integration, **do not select the "No Payment" option**. An invoice will not be created and will cause an error when syncing to QuickBooks Online.
