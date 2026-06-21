---
title: "Additional examples, outside service"
slug: additional-examples-outside-service
source: https://help.paperlessparts.com/s/article/additional-examples-outside-service
topic: "Other / Reference"
captured: 2026-06-19
---

# Additional examples, outside service

> Source: https://help.paperlessparts.com/s/article/additional-examples-outside-service  
> Topic: Other / Reference

# Outside Services

Pricing outside services can be tedious and time consuming. There is nothing more frustrating than having your quotes delayed because of someone else's timeline. However, the pricing of outside services like anodizing, chromate clear, and custom painting usually breaks down in a very simple way for most finish suppliers. They usually use one of two models, a lot-charge, piece-price model, or a slightly more complex (usually used in house) surface area based pricing algorithm. For most situations, the lot-charge piece-price model will suffice. Take a look at how to format your very simple outside service operation for this model:

```
# This outside service operation bases its pricing off of a lot charge and piece price model.
# If the quantity multiplied by the piece price is smaller than the lot charge, than the PRICE
# will be the lot charge. Otherwise it will be the extended piece price.
# You can apply additional lead time by using the added_lead_time variable

lot_charge = var('Lot Charge', 200, 'Lot charge for outside service', currency)
piece_price = var('Piece Price', 2.25, 'Price per unit for the outside service', currency)
added_lead_time = var('Added Lead Time', 3, 'Days of added lead time for outside service', number)

extended_price = part.qty * piece_price
if extended_price < lot_charge:
    PRICE = lot_charge
else:
    PRICE = extended_price

DAYS = added_lead_time
```

The surface area model can be broken down into a very simple operation as well. You simply need to apply a cost per area value to the surface area of the part, which we provide to you in the `part` object.

```
# This outside service operation calculates its pricing on a part surface area model.
# Surface area for most finishing operations is the driving factor for pricing.
# As long as part geometry is not overly complicated to hang on a rack and is not
# extremely large, with the correct price per square inch value, pricing is likely to
# be quite accurate.
# Price is calculated based on an inputted price per unit of surface area.
# Additional lead time can be controlled with the added_lead_time input

units_in()

price_per_sq_inch = var('Price Per Square Inch', 0.01, '', currency)
added_lead_time = var('Added Lead Time', 0, 'Days of added lead time for outside service', number)

PRICE = price_per_sq_inch * part.area * part.qty

DAYS = added_lead_time
```

A standard practice is to apply markups to outside services. Using the power of the pricing dictionary, the following operation can very quickly apply a markup to all of your outside services (if you use one or both of the formats above). This operation will grab the sum of all of the outside service prices and apply the markup you specify.

```
# This applies a markup to outside service price by extracting it from the pricing dictionary.
# You can set your outside service markup with a default value, and modify it at quote time.

markup = var('Markup Percentage', 30, 'Percent markup on outside service cost', number)
outside_service_cost = get_price_value('--outside--')
set_operation_name('Outside Markup: {}%'.format(markup))

PRICE = outside_service_cost * markup / 100
DAYS = 0
```
