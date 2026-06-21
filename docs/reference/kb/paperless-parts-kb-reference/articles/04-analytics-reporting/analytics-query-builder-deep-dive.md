---
title: "Analytics query-builder deep dive"
slug: analytics-query-builder-deep-dive
source: https://help.paperlessparts.com/s/article/analytics-query-builder-deep-dive
topic: "Analytics & Reporting"
captured: 2026-06-19
---

# Analytics query-builder deep dive

> Source: https://help.paperlessparts.com/s/article/analytics-query-builder-deep-dive  
> Topic: Analytics & Reporting

This article goes through each tool available in the query builder (measures and dimensions, segments, time, and filters) and each of the [data entities](#data-entities) available.

# Measures vs. dimensions

- Measures: quantitative data that can be aggregated – data that is *continuous* and can be *measured*
  - Ex: counts of things like accounts, quotes, and orders; costs and prices; percentages
- Dimensions: qualitative data that can be categorized
  - Ex: names of things like accounts, operations, and processes; part numbers
- A query can contain measures, dimensions, or a mix of both. Measures will be aggregated based on dimensions in the query

![A table with “quote count” as a measure and no dimensions will just give the total number of quotes in the selected time range (in this case, all time)](/servlet/rtaImage?eid=ka0Ns0000005cvt&feoid=00N5G00000WB8Hk&refid=0EMNs00000AXcGs)

A table with “quote count” as a measure and **no dimensions** will just give the**total number of quotes**in the selected time range (in this case, all time)A table with “quote count” as a measure and **“accounts name” as a dimension** will give the **total number of quotes for each account** in the selected time range (in this case, all time)

# Segments

Not functional. Do not use.

# Time

Limits your query by time

The “For” grouping designates the time interval for the specific time field enteredThe “By” grouping designates how the measures will be grouped

Available options are any dimensions that are time-based:

- Accounts Created
- Accounts Deleted At
- Component Estimators Date Joined
- Component Quantities Created
- Component Quantities Updated
- Components Created
- Contacts Created
- Contacts Deleted At
- Estimators Date Joined
- Facilities Created
- Facilities Deleted At
- Material Classes Created
- Material Families Created
- Materials Created
- Op Defs Created
- Op Defs Deleted At
- Operations Created
- Order Items Created
- Order Items Delivered By
- Order Items Ships On
- Orders Created
- Orders Last Status Change Dt
- Parts Created
- Processes Created
- Processes Deleted At
- Quote Add Ons Created
- Quote Add Ons Cells Created
- Quote Cells Created
- Quote Custom Cost Category Cells Created
- Quote Discount Cells Created
- Quote Discounts Created
- Quote Items Created
- Quote Items Expired Date
- Quote Profit Item Cells Created
- Quote Profit Items Created
- Quotes Created
- Quotes Digital Last Viewed On
- Quotes Due Date
- Quotes Estimator Assigned On
- Quotes Expired Date
- Quotes Manual RFQ Received Date
- Quotes Quote Started Date
- Quotes Salesperson Assigned On
- Quotes Sent Date
- Quotes Supplier Last Viewed On
- Request for Quote Views Created
- Request for Quote Views Submitted
- Request for Quotes Created
- Request for Quotes Processed On
- Request for Quotes Requested Delivery Date
- Sales Persons Date Joined
- Team Members Date Joined

# Filters

Limits your query for specific entities or time. Most measures and dimensions are available as filter options.

# ![Numeric filters have the following options to filter by. Ex: Quotes Number equals 800](/servlet/rtaImage?eid=ka0Ns0000005cvt&feoid=00N5G00000WB8Hk&refid=0EMNs00000AXe8z)

*Numeric filters have the following options to filter by. Ex: Quotes Number equals 800*

*![Date filters have the following options to filter by. Use YYYY-MM-DD format. For the date ranges, enter two dates in that format](/servlet/rtaImage?eid=ka0Ns0000005cvt&feoid=00N5G00000WB8Hk&refid=0EMNs00000AXeDp)*

*Date filters have the following options to filter by. Use YYYY-MM-DD format. For the date ranges, enter two dates in that format*

# Data entities

The below sections go through each of the data entities available in analytics, and the available measures and dimensions for each entity. The entities are listed alphabetically.

## Accounts

Contacts are groups of buyers or vendors, found on the [contacts page](https://app.paperlessparts.com/contacts?page=1&search=&tab=ACCOUNTS).

**Measures**

- Count (“Accounts Count”): The total number of accounts matching your query

**Dimensions**

- Created (“Accounts Created”): The date and time the account was created
- Deleted at (“Accounts Deleted At”): The date and time the account was deleted
- ERP Code(“Accounts ERP Code”): The ERP code for the account
- Name (“Accounts Name”): The name of the account
- Notes (“Accounts Notes”): Notes about the account
- Phone (“Accounts Phone”): The phone number for the account
- Phone ext (“Accounts Phone Ext”): The phone extension for the account
- Purchased orders enabled (“Accounts Purchased Orders Enabled”): A true/false value indicating whether or not purchase orders are enabled for the account
- Tax exempt (“Accounts Tax Exempt”): A true/false value indicating whether or not the account is tax exempt
- Type (“Accounts Type”): The type of account (such as 'customer' or 'vendor')

## Component estimators

Component estimators are the estimators assigned to the line item. Must be a [Team Member](https://app.paperlessparts.com/team). To use these fields, we recommend adding some dimension to indicate the line item (like part number, or the quote number and line item position).

**Measures**

- None

**Dimensions**

- Date joined (“Component Estimators Date Joined”): The date and time this team member joined your Paperless Parts account
- Email (“Component Estimators Email”): The component estimator’s email
- First name (“Component Estimators First Name”): The component estimator’s first name
- Full name (“Component Estimators Full Name”): The component estimator’s full name
- Is active (“Component Estimators Is Active”): A true/false value indicating whether or not the component estimator is currently active *(note: this field is broken, do not use)*
- Is for API (“Component Estimators Is For API”): *A deprecated concept, do not use*
- Job title (“Component Estimators Job Title”): The component estimator’s job title
- Last name (“Component Estimators Last Name”): The component estimator’s last name

## Component Quantities

Component Quantities are each quantity break on each component (includes both manufactured and child components).

**Measures**

- Average child override cost (“Component Quantities Average Child Override Cost”): The average manual override cost of manufactured components for all quoted components and quantities matching your query
- Average inside cost (“Component Quantities Average Inside Cost”): The average inside cost (not material, outside, or purchased component costs) for all quoted components and quantities matching your query
- Average material cost (“Component Quantities Average Material Cost”): The average cost of raw materials needed to build components for all quoted components and quantities matching your query
- Average outside cost (“Component Quantities Average Outside Cost”): The average outside cost needed to build components for all quoted components and quantities matching your query
- Average purchased component cost (“Component Quantities Average Purchased Component Cost”): The average cost of purchased components needed to build components for all quoted components and quantities matching your query
- Average total cost (“Component Quantities Average Total Cost”): The average total cost of all quoted components and quantities matching your query. For each component quantity, the total is the sum of material, outside, inside, and child override costs
- Average total discount (“Component Quantities Average Total Discount”): The average total discount offered for all quoted components and quantities matching your query. For each component quantity, the total discount is a sum of all discount item values
- Average total discount percentage (“Component Quantities Average Total Discount Percentage”): The average total discount percentage offered for all quoted components and quantities matching your query. For each component quantity, the total discount is a sum of all discount item percentage values
- Average total price (“Component Quantities Average Total Price”): The average of total prices of all components and quantities matching your query
- Average total profit (“Component Quantities Average Total Profit”): The average total profit (total_price_incl_discounts - total_estimated_cost) for all quoted components and quantities matching your query
- Average total profit percentage (“Component Quantities Average Total Profit Percentage”): The average of the “Profit Margin” field ((total_price_incl_discounts - total_estimated_cost) / total_price_incl_discounts) for all quoted components and quantities matching your query
- Average unit profit (“Component Quantities Average Unit Profit”): The average profit per unit of all quoted components and quantities matching your query. A unit profit for a given component quantity is calculated by dividing total profit by the deliver quantities
- Child override cost (“Component Quantities Child Override Cost”): The total cost of child components overrides for all quoted components and quantities matching your query
- Count (“Component Quantities Count”): he total number of component quantity quotes matching the query
- Deliver quantity (“Component Quantities Deliver Quantity”): The sum of all deliver quantities on all components and quantities matching your query. Deliver quantity is the quantity of a component that will be delivered to the customer
- Inside cost (“Component Quantities Inside Cost”): The total inside cost (not material, outside, or purchased component costs) for all quoted components and quantities matching your query
- Make quantity (“Component Quantities Make Quantity”): The sum of all make quantities on all components and quantities matching your query. Make quantity is the quantity of a component that will be made for a quote, including components not delivered to the customer (to account for scrap)
- Manual total unit price (“Component Quantities Manual Total Unit Price”): The sum of all manually entered unit prices on all components and quantities matching your query (note: instead use the“component quantities manual unit price” dimension)
- Material cost (“Components Quantities Material Cost”): The sum of all material costs on all components and quantities matching your query
- Max price (“Component Quantities Max Price”): The maximum total price among all quoted components and quantities matching your query (same as “Component Quantities Max Total Price”)
- Max quantity (“Component Quantities Max Quantity”): The highest quantity among all quoted components and quantities matching your query
- Max total price (“Component Quantities Max Total Price”): The maximum total price of all components and quantities matching your query (same as “Component Quantities Max Price”)
- Max unit cost (“Component Quantities Max Unit Cost”): The maximum unit cost of all components and quantities matching your query
- Max unit price (“Component Quantities Max Unit Price”): The maximum unit price of all components and quantities matching your query
- Min price (“Component Quantities Min Price”): The minimum total price among all quoted components and quantities matching your query (same as “Component Quantities Min Total Price”)
- Min quantity (“Component Quantities Min Quantity”): The lowest quantity among all quoted components and quantities matching your query
- Min total price (“Component Quantities Min Total Price”): The minimum total price of all components and quantities matching your query (same as “Component Quantities Min Total Price”)
- Min unit cost (“Component Quantities Min Unit Cost”): The minimum unit cost of all components and quantities matching your query
- Min unit price (“Component Quantities Min Unit Price”): The minimum unit price of all components and quantities matching your query
- Outside cost (“Component Quantities Outside Cost”): The total outside cost for all quoted components and quantities matching your query
- Price (“Component Quantities Price”): The sum of all the calculated total prices on all components and quantities matching your query (note: instead use the “component quantities total price” dimension)
- Purchased component cost (“Component Quantities Purchased Component Cost”): The sum of all purchased component costs on all components and quantities matching your query
- Total cost (“Component Quantities Total Cost”): The sum of all total costs on all components and quantities matching your query. For each component quantity, the total is the sum of material, outside, inside, and child override costs
- Total discount (“Component Quantities Total Discount”): The sum of all total discounts on all components and quantities matching your query. Total discount is the sum of all discount item values on a given component quantity
- Total discount percentage (“Component Quantities Total Discount Percentage”): The sum of all total discount percentages on all components and quantities matching your query. Total discount percentage is a sum of all discount item percentage values on a given component quantity
- Total profit (“Component Quantities Total Profit”):The sum of total profit (total_price_incl_discounts - total_estimated_cost) for all quoted components and quantities matching your query
- Total profit percentage: (“Component Quantities Total Profit Percentage”): The sum of the “Profit Margin” field ((total_price_incl_discounts - total_estimated_cost) / total_price_incl_discounts) for all quoted components and quantities matching your query (note: instead use the “Profit Margin Percentage” dimension)
- Total total price (“Component Quantities Total Total Price”): The sum of total prices of all components and quantities matching your query
- Unit profit (“Components Quantities Unit Profit”): The sum of the profit per unit of all quoted components and quantities matching your query. A unit profit for a given component quantity is calculated by dividing total profit by the deliver quantities

**Dimensions**

- Calculated unit price (“Component Quantities Calculated Unit Price”): The calculated unit price of the component quantity. This is the calculated “Unit Price” field on a quote (excluding discounts). If the unit price was not overridden and there are no discounts, this will be the same as “Component Quantities Unit Price”
- Created (“Component Quantities Created”): The date and time the component quantity quote was created
- Is most likely won quantity (“Component Quantities Is Most Likely Won Quantity”): A true/false value indicating whether or not the quoted quantity is the most likely to win
- Is most likely won quantity percent (“Component Quantities Is Most Likely Won Quantity Percent”): The percentage odds that the most likely to win quantity will win
- Lead time (“Component Quantities Lead Time”): The lead time for the component
- Manual unit price (“Component Quantities Manual Unit Price”): The manual (overridden) unit price of the component quantity. This is the manual “Unit Price” field on a quote if it was overridden (excluding discounts). If the unit price was not overridden, this field will not be populated
- Profit margin percentage (“Component Quantities Profit Margin Percentage”): The Profit Margin (%) of the component quantity (Profit Margin is (total_price_incl_discounts - total_estimated_cost) / total_price_incl_discounts)
- Quantity (“Component Quantities Quantity”): The quoted quantity for the component
- Total price (“Component Quantities Total Price”): The total price of the component quantity. This is the “Total Price” field on a quote
- Unit cost (“Component Quantities Unit Cost”): The unit cost of the component quantity. This is the “Total estimated unit cost” field on a quote
- Unit price (“Component Quantities Unit Price”): The unit price of the component quantity that is shown on the quote to the buyer. This is the “Unit Price” field on a quote (including discounts). Note that if discounts are on the quote, this field will be different from “Component Quantities Calculated Unit Price” or “Component Quantities Manual Unit Price”, since those are excluding discounts
- Updated (“Component Quantities Updated”): The date and time the component quantity quote was most recently updated

## Components

Components are individual parts (either manufactured, purchased, or assembled) – use Component Quantities instead.

**Measures**

- Count (“Components count”): The total amount of components matching your query
- Innate quantity (“Components Innate Quantity”): The sum of all innate quantities on components matching your query. The “innate quantity” is the count of a specific component in an assembly for a quantity of 1. For example, if one component appears 5 times in an assembly, it’s innate quantity is 5, regardless of the quoted quantity of the assembly *(note: this is the same field as “Parts Innate Quantity”. We recommend using Component Quantities Quantity instead)*
- Max price (“Components Max Price”): The sum of maximum prices of components matching your query *(note: broken field, instead use the “Component Max Total Price” dimension)*
- Max quantity (“Components Max Quantity”): The sum of maximum quantity breaks of components matching your query
- Min price (“Components Min Price”): The sum of minimum prices of components matching your query *(note: broken field, instead use the “Component Min Total Price” dimension)*
- Min quantity (“Components Min Quantity”): The sum of minimum quantity breaks of components matching your query

**Dimensions**

- Created (“Components Created”): The date and time the component was created
- Description (“Components Description”): The description of the component
- Is assembled (“Components Is Assembled”): This field is broken, do not use. Use “Parts Is Assembly” instead.
- Is root component (“Components Is Root Component”): A true/false value indicating whether or not the component is a root component on an assembly. The root component can be thought of as the component that the customer is requesting, the component at the line item level. The opposite of a root component is a child component
- Max total price (“Components Max Total Price”): The maximum total price of the component (the largest “Component Quantities Total Price” on a line item)
- Max unit cost (“Components Max Unit Cost”): The maximum unit cost of the component (the largest “Component Quantities Unit Cost” on a line item)
- Max unit price (“Components Max Unit Price”): The maximum unit price of the component (the largest “Component Quantities Unit Price” on a line item)
- Maximum price (“Components Maximum Price”): Same as “Components Max Total Price”, use that dimension instead
- Maximum quantity (“Components Maximum Quantity”): The maximum quantity break on the component
- Min total price (“Components Min Total Price”): The minimum total price of the component (the smallest “Component Quantities Total Price” on a line item)
- Min unit cost (“Components Min Unit Cost”): The minimum unit cost of the component (the smallest “Component Quantities Unit Cost” on a line item)
- Min unit price (“Components Min Unit Price”): The minimum unit price of the component (the smallest “Component Quantities Unit Price” on a line item)
- Minimum price (“Components Minimum Price”): Same as “Components Min Total Price”, use that dimension instead
- Minimum quantity (“Components Minimum Quantity”): The minimum quantity break on the component
- Obtain method (“Components Obtain Method”): The obtain method of the component (manufactured or purchased)
- Orientation (“Components Orientation”): This field is broken, do not use
- Part ID (“Components Part ID”): The part ID of the component. Components that were created through duplication (such as duplicating the quote item or quote, or importing historical work) will have the same part ID, even if they are in different quotes or quote items
- Part number (“Components Part Number”): The part number of the component
- Revision (“Components Revision”): The revision of the component

## Contacts

Contacts are individual buyers or vendors, found on the [contacts page](https://app.paperlessparts.com/contacts?page=1&search=&tab=ACCOUNTS).

**Measures**

- Count (“Contacts Count”): The total amount of contacts matching your query

**Dimensions**

- Created (“Contacts Created”): The date and time this contact was added to Paperless Parts
- Deleted at (“Contacts Deleted At”): If applicable, the date and time this contact was removed from Paperless Parts
- Email (“Contacts Email”): The contact's email address
- Name (“Contacts Name”): The contact's full name
- Notes (“Contacts Notes”): Notes about the contact
- Phone (“Contacts Phone”): The contact’s phone numner
- Phone ext (“Contacts Phone Ext”): The contact’s phone extension

## Estimators

Estimators are set on a quote. Must be a [Team Member](https://app.paperlessparts.com/team).

**Measures**

- Count (“Estimators Count”): The total amount of estimators matching your query

**Dimensions**

- Date joined (“Estimators Date Joined”): The date and time this estimator joined Paperless Parts
- Email (“Estimators Email”): The estimator's email
- First name (“Estimators First Name”): The estimator's first name
- Full name (“Estimators Full Name”): The estimator's full name
- Is active (“Estimators Is Active”): A true/false value indicating whether or not the estimator is currently active (note: this field is broken, do not use)
- Is for API (“Estimators Is For API”): *A deprecated concept, do not use*
- Job title (“Estimators Job Title”): The estimator's job title
- Last name (“Estimators Last Name”): The estimator's last name

## Facilities

Facilities on accounts in the Contacts page. NOT the facilities set in the [settings page](https://app.paperlessparts.com/settings/company/supplier_facilities).

**Measures**

- Count (“Facilities Count”): The number of facilities matching your query

**Dimensions**

- Attention (“Facilities Attention”): The name of the contact for this facility
- Created (“Facilities Created”): The date and time this facility was added to Paperless Parts
- Deleted at (“Facilities Deleted At”): If applicable, the date and time this facility was removed from Paperless Parts
- Name (“Facilities Name”): The name of the facility

## Material Classes

Material Classes are Composite, Metal, Polymer, Sand, Wax, and Additive, found on the Configure page under “[Materials](https://app.paperlessparts.com/processes/materials)”.

**Measures**

- Count (“Material Classes Count”): The total amount of material classes matching your query

**Dimensions**

- Created (“Material Classes Name”): The date and time this material class was added to Paperless Parts
- Name (“Material Classes Name”): The name of the material class

## Material Families

Material Families are Aluminum, Alloy Steel, Stainless Steel, etc., found on the Configure page under each Material Class in the “[Materials](https://app.paperlessparts.com/processes/materials)” tab.

**Measures**

- Count (“Material Families Count”): The total amount of material families matching your filters

**Dimensions**

- Created (“Material Families Created”): The date and time this material family was added to Paperless Parts
- Name (“Material Families Name”): The name of the material family (ex: Aluminum, Stainless Steel, etc.)

## Materials

Materials are specific materials (ex: Aluminum 6061-T6), found on the Configure page under each Material Class/Family in the “[Materials](https://app.paperlessparts.com/processes/materials)” tab.

**Measures**

- Count (“Materials Count”): The total amount of materials matching your query

**Dimensions**

- Created (“Materials Created”): The date and time this material was added to Paperless Parts
- Name (“Materials Name”): The name of the material
- Spec URL (“Materials Spec URL”): *A deprecated concept, do not use (breaks the query)*

## Op Defs

**None of these fields work.** Use the “Operations” measures and dimensions instead.

**Measures**

- Count (“Op Defs Count”): The total amount of operation definitions matching your filters
- Purchase Price (“Op Defs Purchase Price”)

**Dimensions**

- Category (“Op Defs Category”): The category for this operation definition ('operation' or 'material')
- Costing context factory class name (“Op Defs Costing Context Factory Class Name”): The name of the class that will be used to create the costing context for this operation definition (ex: 'marketplace' or 'operation')
- Created (“Op Defs Created”): The date and time this operation definition was added to Paperless Parts
- Deleted at (“Op Defs Deleted At”): If applicable, the date and time this operation definition was removed from Paperless Parts
- Is outside service (“Op Defs Is Outside Service”): A true/false value indicating whether or not this operation definition is for an outside service
- Name (“Op Defs Name”): The name of this operation definition
- Part modifiers (“Op Defs Part Modifiers”): Specific values for parts (ex: additive runtime or support volume coefficients) that are required for this operation definition
- Runtime display units (“Op Defs Runtime Display Units”): The unit of measure displayed for the operation definition's runtime (hr, min, sec)
- Setup time display units (“Op Defs Setup time Display Units”): The unit of measure displayed for the operation definition's setup time (hr, min, sec)

## Operations

Operations are found on the Configure Page under “[Operations](https://app.paperlessparts.com/processes/operations)”.

**Measures**

- Count (“Operations Count”): The total amount of operations matching your query
- Overrides count (“Operations Overrides Count”): The total amount of operations with overrides matching your query. This only includes overrides made to the operation calculation itself, NOT overrides to the total cost of the operation.

In this example, only CNC | CMM and Generic | Final Inspection will be counted towards Operations Overrides Count

**Dimensions**

- Avg part X (“Operations Avg Part X”): *This field is broken, do not use*
- Category (“Operations Category”): The category of the operation (ex: “operation” or “material”)
- Created (“Operations Created”): The date and time the operation was added to Paperless Parts
- Is finish (“Operations Is Finish”): A true/false value indicating whether or not the operation is a finish
- Is from op factory (“Operations Is From Op Factory”): A true/false value indicating if the operation was generated from the Process set on the line item (false would indicate an operation manually added to the quote)
- Is outside service (“Operations Is Outside Service”): A true/false value indicating whether or not the operation is an outside service
- Name (“Operations Name”): The dynamic name of the operation (the *dynamic* name is the name of an operation after any updates to the operation name in P3L. On the other hand, the *definition* name of the operation is what appears listed in the Configure page. For example, if you have a “Bar Stock” operation in your list of operations, but have the operation configured so that the name of the operation on a quote updates to the name of the material and the stock size needed for that part, the *definition* name of the operation is “*Bar Stock*” and the *dynamic* name would be the *updated name with the material name and stock size*).
- Notes (“Operations Notes”): The notes about the operation
- Overrides (“Operations Overrides”): *A deprecated concept, do not use*
- Pricing context (“Operations Pricing Context”): *A deprecated concept, do not use*
- Runtime display units (“Operations Runtime Display Units”): The unit of measure displayed for the operation's runtime
- Setup time display units (“Operations Setup Display Units”): The unit of measure displayed for the operation's setup time

## Order Items

Order items are individual order lines on an order.

**Measures**

- Count (“Order Items Count”): The total amount of order items matching your query
- Expedites fee (“Order Items Expedites Fee”): The sum of all expedite fees on order items matching your query
- Price (“Order Items Price”): The sum of all prices on order items matching your query
- Quantity (“Order Items Quantity”): The sum of all quantities on order items matching your query
- Shipping price (“Order Items Shipping Price”): The sum of all shipping prices on order items matching your query

**Dimensions**

- Created (“Order Items Created”): The date and time this order item was created
- Delivered by (“Order Items Delivered By”): *(deprecated concept, do not use)*
- ERP ID (“Order Items ERP ID”): *(deprecated concept, do not use)*
- Line items (“Order Items Line Items”): *(deprecated concept, do not use)*
- Ships on (“Order Items Ships On”): The date and time when this order item ships
- Total price (“Order Items Total Price”): The total price of the order item
- Unit price (“Order Items Unit Price”): The unit price of the order item

## Orders

Orders are found on the [Orders Page](https://app.paperlessparts.com/orders/all). Each Order contains Order Items.

**Measures**

- Average price (“Orders Average Price”): The average of all total prices on orders matching your query
- Count (“Orders Count”): The total amount of orders matching your query
- Total expedite fees (“Orders Total Expedite Fees”): The sum of all expedite fees on all orders matching your query
- Total order items (“Orders Total Order Items”): The total number of order items on all orders matching your query
- Total price (“Orders Total Price”): The sum of all total prices on orders matching your query

**Dimensions**

- Created (“Orders Created”): The date and time this order was created
- Expedites fee (“Orders Expedites Fee”): The sum of all expedite fees on order items on this order
- Last status changed (“Orders Last Status Change Dt”): The date and time this order’s status last changed
- Number (“Orders Number”): The order number
- Order Items Count (“Orders Order Items Count”): The total number of order items on the order
- Status (“Orders Status”): The order status (confirmed, cancelled, etc.)

## Parts

Parts are made up of components. An assembled part has many components, or a part can have one component.

**Measures**

- Count (“Parts Count”): The total amount of parts matching your query
- Innate quantity (“Parts Innate Quantity”): The sum of all innate quantities on parts matching your query. The “innate quantity” is the count of a specific part in an assembly for a quantity of 1. For example, if one part appears 5 times in an assembly, it’s innate quantity is 5, regardless of the quoted quantity of the assembly *(note: this is the same field as “Components Innate Quantity”. We recommend using Component Quantities Quantity instead)*
- X Avg (“Parts X Avg”): The average size in millimeters in the x dimension among all parts matching your query
- X Max (“Parts X Max”): The maximum size in millimeters in the x dimension among all parts matching your query
- X Min (“Parts X Min”): The minimum size in millimeters in the x dimension among all parts matching your query
- Y Avg (“Parts Y Avg”): The average size in millimeters in the y dimension among all parts matching your query
- Y Max (“Parts Y Max”): The maximum size in millimeters in the y dimension among all parts matching your query
- Y Min (“Parts Y Min”): The minimum size in millimeters in the y dimension among all parts matching your query
- Z Avg (“Parts Z Avg”): The average size in millimeters in the z dimension among all parts matching your query
- Z Max (“Parts Z Max”): The maximum size in millimeters in the z dimension among all parts matching your query
- Z Min (“Parts Z Min”): The minimum size in millimeters in the z dimension among all parts matching your query

**Dimensions**

- Area mm (“Area mm”): The surface area of the part in square millimeters
- Created (“Parts Created”): The date and time the part was created
- Description (“Parts Description”): The description of the part
- File Type (“Parts File Type”): The file type of the part's primary file (ex: print, STEP, vector)
- Filename (“Parts Filename”): The name of the part's primary file
- Is Archived (“Parts Is Archived”): A true/false value indicating whether or not the part is archived
- Is Assembly (“Parts Is Assembly”): A true/false value indicating whether or not the part is part of an assembly. Must have the blue “A” badge to be an assembly. A manufactured component with hardware is not an assembly
- Is Export Controlled (“Parts Is Export Controlled”): A true/false value indicating whether or not the part is export controlled (ITAR)
- Is Manual (“Parts Is Manual”): A true/false value indicating whether or not the part was manually created (through the “Create blank line item” workflow, not created from a file)
- Is Manual Child (“Parts Is Manual Child”): A true/false value indicating whether or not the part is the child of a manually created part. Since this dimension is on the part level (and not the component level), this will only be true if a manual child component is converted to a line item by moving the child component up one or more levels.
- Is Root Part (“Parts Is Root Part”): A true/false value indicating whether or not the part is a root part on an assembly. The root part can be thought of as the part that the customer is requesting, the part at the line item level. The opposite of a root part is a child part
- Part Number (“Parts Part Number”): The part number of the part
- Process Tag (“Parts Process Tag”): The manufacturing process for the part
- Revision (“Parts Revision”): The revision of the part
- Size X mm (“Parts Size X mm”): The size of the part in the x dimension in millimeters
- Size Y mm (“Parts Size Y mm”): The size of the part in the y dimension in millimeters
- Size Z mm (“Parts Size Z mm”): The size of the part in the z dimension in millimeters
- Type (“Parts Type”): The type of the part (ex: assembled, purchased, manufactured) (note: this field is broken, do not use)
- Volume mm (“Parts Volume mm”): The volume of the part in cubic millimeters

## Processes

Processes are found on the Configure Page under “[Processes](https://app.paperlessparts.com/processes)”.

**Measures**

- Count (“Processes Count”): The total amount of processes matching your query

**Dimensions**

- Created (“Processes Created”): The date and time this process was added to Paperless Parts
- Deleted at (“Processes Deleted At”): If applicable, the date and time this process was deleted from Paperless Parts
- External name (“Processes External Name”): The external name of the process, shown on the SmartRFQ form and Digital Quote
- Is default purchased component process (“Processes Is Default Purchased Component Process”): A true/false value indicating whether or not the process is the default purchased component process
- Name (“Processes Name”): The name of the process
- Op factory (“Processes Op Factory”): *A deprecated concept, do not use*
- Op factory class name (“Processes Op Factory Class Name”): The operations factory class name of the process (such as 'manufacturing' or 'custom')
- Public (“Processes Public”): A true/false value indicating whether or not the process is public on the SmartRFQ form
- Published (“Processes Published”): *A deprecated concept, do not use*
- Use list display for process materials (“Processes Use List Display For Process Materials”): A true/false value indicating whether or not the process uses list display for process materials

## Quote Add Ons

Add-ons are found in the Configure Page under “[Add ons](https://app.paperlessparts.com/processes/add_ons)”. Quote Add Ons represent each add-on on a quote or line item level, while Quote Add On Cells represent each add-on cost, by quantity.

**Measures**

- Count (“Quote Add Ons Count”): The total amount of add-ons matching your query

**Dimensions**

- Created (“Quote Add Ons Created”): The date and time this quote add-on was created
- Is Required (“Quote Add Ons Is Required”): A true/false value indicating whether the quote add-on is required
- Is from add on factory (“Quote Add Ons Is From Add On Factory”): A true/false value indicating if the add-on was generated from the Process set on the line item (false would indicate an add-on manually added to the quote)
- Name (“Quote Add Ons Name”): The name of the quote add-on
- Overrides (“Quote Add Ons Override”): *A deprecated concept, do not use*
- Overrides audit (“Quote Add Ons Override Audit”): *A deprecated concept, do not use (crashes the page)*
- Pricing context (“Quote Add Ons Pricing Context”): *A deprecated concept, do not use*

## Quote Add On Cells

Add-ons are added to a line item, and represent a one-time cost that is not included in the unit price. Quote Add On Cells represent each add-on cost, by quantity, while Quote Add Ons represent each add-on on a quote or line item level

**Measures**

- Calculated price (“Quote Add On Cells Calculated Price”): The sum of all calculated prices on all quote add-on cells matching your query
- Count (“Quote Add On Cells Count”): The total amount of quote add-on cells matching your query (if there are multiple quantity breaks on the line item, each quantity break can have its own add on cell)
- Manual unit price (“Quote Add On Cells Manual Unit Price”): The sum of all manually-entered unit prices on all quote add-on cells matching your query
- Manual price (“Quote Add On Cells Manual Price”): The sum of manually-entered total prices on each quote add-on cell matching your query

**Dimensions**

- Created (“Quote Add On Cells Created”): The date and time this quote add-on cell was created (by being added to the quote, either manually or generated by a process)
- Overrides audit (“Quote Add On Cells Overrides Audit”): *A deprecated concept, do not use (crashes the page)*

## Quote Cells

A quote cell is a cell in the quote item costing tables used to record and display information about operations. These are not very useful. Use Component Quantities instead.

**Measures**

- Calculated price (“Quote Cells Calculated Price”): The calculated cost of an operation for each quantity without overrides to the total cost (in other words, what is calculated using P3L, even if P3L variables are overridden within the operation drawer. Excludes overrides to quantity-specific costs). *Instead use the “Component Quantities Calculated Unit Price” dimension*
- Count (“Quote Cells Count”): The total amount of quote cells matching your query
- Manual price (“Quote Cells Manual Price”): The total dollar amount of quantity-specific overrides on an component (not including overrides made to P3L variables or setup/runtime)
- Manual unit price (“Quote Cells Manual Unit Price”): *Instead use the “Component Quantities Manual Unit Price” dimension*
- Price (“Quote Cells Price”): *Instead use the “Component Quantities Total Price” dimension*

**Dimensions**

- Created (“Quote Cells Created”): The date and time this quote cell was created
- Overrides audit (“Quote Cells Overrides Audit”): *A deprecated concept, do not use (crashes the page)*

## Quote Custom Cost Category Cells

Only for Paperless Parts customers who have access to Custom Cost Categories, which is a beta feature still in development.

**Measures**

- Average cost (“Quote Custom Cost Category Cells Average Cost”): The average cost of custom cost category cells matching your query
- Average cost percentage (“Quote Custom Cost Category Cells Average Cost Percentage”): The average cost percentage custom cost category cells matching your query
- Count (“Quote Custom Cost Category Cells Count”): The total amount of custom cost category cells matching your query
- Total cost (“Quote Custom Cost Category Cells Total Cost”): The total cost of custom cost category cells matching your query

**Dimensions**

- Color (“Quote Custom Cost Category Cells Color”): The color of the custom cost category
- Cost (“Quote Custom Cost Category Cells Cost”): The cost of the custom cost category
- Cost percentage (“Quote Custom Cost Category Cells Cost Percentage”): The cost percentage of the custom cost category
- Created (“Quote Custom Cost Category Cells Created”): The date and time this quote profit item cell was created (by being added to the quote, either manually or generated by a process)
- Name (“Quote Custom Cost Category Cells Name”): The name of the custom cost category

## Quote Discount Cells

Discounts are created in the Configure Page under “[Discounts](https://app.paperlessparts.com/processes/discounts)” for accounts who have turned on the discounts feature in the [Settings Page](https://app.paperlessparts.com/settings/digital_quote/discounts). Quote Discount Cells represent each discount amount, by quantity, while Quote Discounts represent each discount on a quote or line item level.

**Measures**

- Count (“Quote Discount Cells Count”): The total amount of quote discount cells matching your query
- Discount (“Quote Discount Cells Discount”): *A deprecated concept, do not use (breaks the query)*
- Manual percentage (“Quote Discount Cells Manual Percentage”): The sum of all manually entered discount percentages on all quote discount cells matching your query
- Percentage (“Quote Discount Cells Percentage”): The sum of all percentages on all quote discount cells matching your query. The percentage for a quote discount cell is the manually entered discount percentage when one is available, otherwise it is the calculated discount percentage

**Dimensions**

- Created (“Quote Discount Created”): The date and time this quote discount cell was created
- Overrides audit (“Quote Discount Overrides Audit”):*A deprecated concept, do not use (crashes the page)*

## Quote Discounts

Discounts are created in the Configure Page under “[Discounts](https://app.paperlessparts.com/processes/discounts)” for accounts who have turned on the discounts feature in the [Settings Page](https://app.paperlessparts.com/settings/digital_quote/discounts).

**Measures**

- Count (“Quote Discounts Count”): The total amount of quote discounts matching your query

**Dimensions**

- Created (“Quote Discounts Created”): The date and time the quote discount was added to Paperless Parts
- Is from discount factory (“Quote Discounts Is From Discount Factory”): A true/false value indicating if the discount was generated from the Process set on the line item (false would indicate a discount manually added to the quote)
- Name (“Quote Discounts Name”): The name of the quote discount
- Overrides (“Quotes Discount Overrides”): *A deprecated concept, do not use (not populated)*
- Overrides audit (“Quote Discounts Override Audit”): *A deprecated concept, do not use (not populated)*
- Pricing context (“Quote Discounts Pricing Context”): *A deprecated concept, do not use (not populated)*

## Quote items

Quote items are individual quote lines on a quote.

**Measures**

- Count (“Quote Items Count”): The total amount of quote items matching your query
- Won count (“Quote Items Won Count”): The total amount of quote items that were won matching your query

**Dimensions**

- Created (“Quote Items Created”): The date and time the quote item was created
- Expired date (“Quote Items Expired Date”): The date and time the quote item expired
- Export controlled (“Quote Items Export Controlled”): A true/false value indicating whether or not this quote item includes export controlled (ITAR) data
- Position (“Quote Items Position”): The position of the quote item in the quote
- Was won (“Quote Items Was Won”): A true/false value indicating whether or not the quote item was won
- Workflow status ('Quote Items Workflow Status”): The workflow status of the quote item (completed, on hold, etc.)

## Quote Profit Item Cells

Profit Items are created in the Configure Page under “[Pricing](https://app.paperlessparts.com/processes/pricing)”. Quote Profit Item Cells represent each profit item amount, by quantity, while Quote Profit Items represent each profit item on a quote or line item level.

**Measures**

- Average percentage (“Quote Profit Item Cells Average Percentage”): The average of all percentages on all quote profit item cells matching your queries. The percentage for a quote profit item cell is the manually entered profit percentage when one is available, otherwise it is the calculated profit percentage
- Calculated percentage (“Quote Profit Item Cells Calculated Percentage”): Do not use (breaks the query)
- Calculated profit (“Quote Profit Item Cells Calculated Profit”): The sum of all calculated profits ($) on all quote profit item cells matching your query
- Count (“Quote Profit Item Cells Count”): The total amount of quote profit item cells matching your query
- Manual percentage (“Quote Profit Item Cells Manual Percentage”): The sum of all manually entered profit percentages on all quote profit item cells matching your query
- Manual profit (“Quote Profit Item Cells Manual Profit”): The sum of all manually entered profits ($) on all quote profit item cells matching your query
- Percentage (“Quote Profit Item Cells Percentage”): The sum of all percentages on all quote profit item cells matching your queries. The percentage for a quote profit item cell is the manually entered profit percentage when one is available, otherwise it is the calculated profit percentage
- Profit (“Quote Profit Item Cells Profit”): The sum of all profits ($) on all quote profit item cells matching your query. The profit for a quote profit item cell is the manually entered profit when one is available, otherwise it is the calculated profit

**Dimensions**

- Created (“Quote Profit Item Cells Created”): The date and time this quote profit item cell was created (by being added to the quote, either manually or generated by a process)
- Overrides audit (“Quote Profit Item Cells Overrides Audit”): *A deprecated concept, do not use (never populated)*

## Quote Profit Items

Profit Items are created in the Configure Page under “[Pricing](https://app.paperlessparts.com/processes/pricing)”. Quote Profit Items represent each profit item on a quote or line item level, while Quote Profit Item Cells represent each profit item amount, by quantity.

**Measures**

- Count (“Quote Profit Items Count”): The total amount of quote profit items matching your query

**Dimensions**

- Category (“Quote Profit Items Category”): The category for the quote profit item (such as 'inside' or 'material')
- Created (“Quote Profit Items Created”): The date and time the quote profit item was created
- Is from profit item factory (“Quote Profit Items Is From Profit Item Factory”): A true/false value indicating if the profit item was generated from the Process set on the line item (false would indicate a profit item manually added to the quote)
- Name (“Quote Profit Items Name”): The name of the quote profit item
- Overrides (“Quote Profit Items Overrides”): *A deprecated concept, do not use (never populated)*
- Overrides audit (“Quote Profit Items Overrides Audit”): *A deprecated concept, do not use (never populated)*
- Pricing context (“Quote Profit Items Pricing Context”): *A deprecated concept, do not use (never populated)*

## Quotes

Quotes are found on the [Quotes Page](https://app.paperlessparts.com/quotes). Each Quote contains Quote Items.

**Measures**

- Average draft to send time (“Quotes Average Draft To Send Time”): The average number of hours it takes to send a quote after it is created
- Average draft to send time days (“Quotes Average Draft To Send Time Days”): The average number of days it takes to send a quote after it is created (to 2 decimals)
- Average due date to send days (“Quotes Average Due Date To Send Days”): The average number of days between the due date and the send date (a positive number indicates the quote was sent before the due date (on time))
- Average due date to send hours (“Quotes Average Due Date To Send Hours”): The average number of hours between the due date and the send date (a positive number indicates the quote was sent before the due date (on time))
- Average maximum subtotal (“Quotes Average Maximum Subtotal”): The average maximum subtotal of all quotes matching your query
- Average maximum total (“Quotes Average Maximum Total”): The average maximum total of all quotes matching your query
- Average minimum subtotal (“Quotes Average Minimum Subtotal”): The average minimum subtotal of all quotes matching your query
- Average minimum total (“Quotes Average Minimum Total”): The average minimum total of all quotes matching your query
- Average quote items (“Quotes Average Quote Items”): The average amount of quote items per quote matching your query
- Average received to draft time hours (“Quotes Average Received To Draft Time Hours”): The average number of hours it takes to draft a quote after it is received
- Average received to send time days (“Quotes Average Received To Send Time Days”): The average number of days it takes to send a quote after it is received (to 2 decimals)
- Average received to send time hours (“Quotes Average Received To Send Time Hours”): The average number of hours it takes to send a quote after it is received
- Count (“Quotes Count”): The total amount of quotes matching your filter
- Maximum subtotal (“Quotes Maximum Subtotal”): The sum of all maximum subtotals on all quotes matching your query
- Maximum total (“Quotes Maximum Total”): The sum of all maximum totals on all quotes matching your query
- Minimum subtotal (“Quotes Minimum Subtotal”): The sum of all minimum subtotals on all quotes matching your query
- Minimum total (“Quotes Minimum Total”): The sum of all minimum totals on all quotes matching your query
- Shipping cost (“Quotes Shipping Cost”): *A deprecated concept, do not use (shipping is dynamically calculated based on the UPS API)*
- Tax cost (“Quotes Tax Cost”): *A deprecated concept, do not use*
- Win rate (“Quotes Win Rate”): The percentage of quotes that were won among all quotes matching your query. This is the number of accepted quote items divided by the total number of quote items

**Dimensions**

- Created (“Quotes Created”): The date and time the quote was created
- Digital last viewed on (“Quotes Digital Last Viewed On”): The date and time the Digital Quote was last viewed by a buyer
- Draft to send days (“Quotes Draft To Send Days”): The number of days between the quote being created and sent
- Draft to send hours (“Quotes Draft To Send Hours”): The number of hours between the quote being created and sent
- Draft to send time range (“Quotes Draft To Send Time Range”): A categorization of the time range between when the quote was created and when it was sent:
  - Less Than 1 Hour
  - 1-4 Hours
  - 4-12 Hours
  - 12-24 Hours
  - 1-2 Days
  - 2-5 Days
  - 5+ Days
- Due date (“Quotes Due Date”): The date and time the quote is due
- Due date to send hours (“Quotes Due Date To Send Hours”): The number of hours between the due date and the send date (a positive number indicates the quote was sent before the due date (on time))
- Estimator assigned on (“Quotes Estimator Assigned On”): The date and time the estimator was assigned to the quote
- Expired date (“Quotes Expired Date”): The date and time the quote expired
- Lead time display units (“Quotes Lead Time Display Units”): The unit of time used to display the lead time (weeks, business_days, calendar_days)
- Manual RFQ received date (“Quotes Manual RFQ Received Date”): The date and time the RFQ was received (either manually entered or populated automatically from the email RFQ)
- Mark sent or finalized (“Quotes Mark Sent Or Finalized”): A value indicating whether the quote was finalized and sent in the platform ('finalized') or marked as sent and sent outside of Paperless ('mark sent')
- Number (“Quotes Number”): The quote number assigned to the quote
- Private notes (“Quotes Private Notes”): The private (“internal”) notes on the quote
- Sent On Time (“Quotes Sent On Time”): A true/false field if the quote was sent before the quote due date. TRUE means the quote was sent before the due date (and is on-time), FALSE means the quote was sent after the due date (and is late)
- Quote started date (“Quotes Quote Started Date”): The date and time the quote was started
- Received to draft days (“Quotes Received To Draft Days”): The number of days between the quote being received and created
- Received to draft hours (“Quotes Received To Draft Hours”): The number of hours between the quote being received and created
- Received to draft time range (“Quotes Received To Draft Time Range”): A categorization of the time range between when the quote was received and when it was created:
  - Less Than 1 Hour
  - 1-4 Hours
  - 4-12 Hours
  - 12-24 Hours
  - 1-2 Days
  - 2-5 Days
  - 5+ Days
- Received to send days (“Quotes Received To Send Days”): The number of days between the quote being received and sent
- Received to send hours (“Quotes Received To Send Hours”): The number of hours between the quote being received and sent
- Received to send time range (“Quotes Received To Send Time Range”): A categorization of the time range between when the quote was created and when it was sent:
  - Less Than 1 Hour
  - 1-4 Hours
  - 4-12 Hours
  - 12-24 Hours
  - 1-2 Days
  - 2-5 Days
  - 5-14 Days
  - 2+ Weeks
- Revision (“Quotes Revision”): The revision number assigned to the quote
- RFQ number (“Quotes RFQ Number”): The RFQ number assigned on the quote
- Salesperson assigned on (“Quotes Salesperson Assigned On”): The date and time the salesperson was assigned to the quote
- Send from facility (“Quotes Send From Facility”): The send from facility on the quote
- Sent date (“Quotes Sent Date”): The date and time the quote was sent
- Status (“Quotes Status”): The status of the quote (such as 'lost', 'draft', etc)
- Supplier last viewed on (“Quotes Supplier Last Viewed On”): The date and time the supplier last viewed the Digital Quote (by clicking the “Preview” button)

## Request for Quote Views

Form views to the SmartRFQ form. A view may or may not actually be submitted. Connected to the “Request for Quote” table through the “Request for Quote Views Uuid” and “Request for Quotes RFQ View Uuid” fields.

**Measures**

- Count (“Request for Quote Views Count”): The total amount of RFQ views matching your query

**Dimensions**

- Created (“Request for Quote Views Created”): The date and time the RFQ view was created, which is when form submissions began
- Has finished contact info (“Request for Quote Views Has Finished Contact Info”): A true/false value indicating whether or not the user has finished the contact info section of the RFQ form
- Has finished part details (“Request for Quote Views Has Finished Part Details”): A true/false value indicating whether or not the user has finished the part details section of the RFQ form
- Has requested delivery date (“Request for Quote Views Has Requested Delivery Date”): A true/false value indicating whether or not the user has requested a delivery date in the RFQ form
- Has started contact info (“Request for Quote Views Has Started Contact Info”): A true/false value indicating whether or not the user has started the contact info section of the RFQ form
- Has started part details (“Request for Quote Views Has Started Part Details”): A true/false value indicating whether or not the user has started the part details section of the RFQ form
- Has submitted additional notes (“Request for Quote Views Has Submitted Additional Notes”): A true/false value indicating whether or not the user has submitted additional notes in the RFQ form
- Has submitted file (“Request for Quote Views Has Submitted File”): A true/false value indicating whether or not the user has submitted a file in the RFQ form
- Has submitted source (“Request for Quote Views Has Submitted Source”): A true/false value indicating whether or not the user has submitted a source in the RFQ form
- Submitted (“Request for Quote Views Submitted”): If applicable, the date and time the RFQ view was submitted, which is when they submitted their RFQ form
- UUID (“Request for Quote Views Uuid”): A unique identifier for each SmartRFQ form view

## Request for Quotes

Form submissions to the SmartRFQ form. Users can select which fields are shown in this in the [Settings Page](https://app.paperlessparts.com/settings/quote_creation/smart_rfq_settings).

**Measures**

- Count (“Request for Quotes Count”): The total amount of RFQs created from the SmartRFQ form matching your query

**Dimensions**

- Business name (“Request for Quotes Business Name”): The business name entered in the SmartRFQ form submission
- Created (“Request for Quotes Created”): The date and time this SmartRFQ form was submitted
- Description (“Request for Quotes Description”): The description entered in the SmartRFQ form submission (the answer for “What else should we know about your project?”)
- Email (“Request for Quotes Email”): The email address to entered in the SmartRFQ form submission
- Export controlled (“Request for Quotes Export Controlled”): A true/false value indicating whether or not this SmartRFQ form submission includes export controlled (ITAR) data
- First name (“Request for Quotes First Name”): The first name entered in the SmartRFQ form submission
- Last name (“Request for Quotes Last Name”): The last name entered in the SmartRFQ form submission
- Marketing source (“Request for Quotes Marketing Source”): The marketing source that led to this SmartRFQ form submission (based on utm parameters)
- Other material (“Request for Quotes Other Material”): A true/false value indicating whether or not this quote should use a material other than the one specified (note: this field no longer exists on the SmartRFQ form)
- Phone (“Request for Quotes Phone”): The phone number entered in the SmartRFQ form submission
- Phone ext (“Request for Quotes Phone Ext”): The phone number extension entered in the SmartRFQ form submission
- Processed on (“Request for Quotes Processed On”): The date and time this SmartRFQ form submission was processed into a quote (should be about <1 after the “Request for Quotes Created”)
- Provide best options (“Request for Quotes Provide Best Options”): A true/false value indicating whether or not the customer wants to receive the best options for their part (note: this field no longer exists on the SmartRFQ form)
- Referrer (“Request for Quotes Referrer”): The person or business that referred the contact on this SmartRFQ form submission (the answer for “How did you hear about us?”)
- Requested delivery date (“Request for Quotes Requested Delivery Date”): The date and time for this SmartRFQ form submission’s customer requested delivery
- RFQ number (“Request for Quotes RFQ Number”): The RFQ number assigned to the quote created from the SmartRFQ form submission
- RFQ view Uuid (“Request for Quotes RFQ View Uuid”): The unique ID that ties an RFQ submission with the Request for Quote Views (see section below)

## Salespersons

Salespersons are set on a quote. Must be a [Team Member](https://app.paperlessparts.com/team).

**Measures**

- Count (“Sales Persons Count”): The total amount of salespersons matching your query

**Dimensions**

- Date joined (“Sales Persons Date Joined”): The date and time this salesperson joined Paperless Parts
- Email (“Sales Persons Email”): The salesperson’s email
- First name (“Sales Persons First Name”): The salesperson’s first name
- Full name (“Sales Persons Full Name”): The salesperson’s full name
- Is active (“Sales Persons Is Active”): A true/false value indicating whether or not the salesperson is currently active (note: this field is broken, do not use)
- Is for API (“Sales Persons Is for API”): *A deprecated concept, do not use*
- Job title (“Sales Persons Job Title”): The salesperson’s job title
- Last name (“Sales Persons Last Name”): The salesperson’s last name

## Team members

Team members are users of the Paperless Parts account, listed in the [Teams Page](https://app.paperlessparts.com/team).

**Measures**

- Count (“Team members count”): The total amount of team members matching your query

**Dimensions**

- Date joined (“Team Members Date Joined”): The date and time this team member joined your Paperless Parts account
- Email (“Team Members Email”): The team member’s email address
- First name (“Team Members First Name”): The team member's first name
- Full name (“Team Members Full Name”): The team member's full name
- Is active (“Team Members Is Active”): A true/false value indicating whether or not the team member is currently active (note: this field is broken, do not use)
- Is for API (“Team Members Is for API”): *A deprecated concept, do not use*
- Job title (“Team Members Job Title”): The team member’s job title
- Last name (“Team Members Last Name”): The team member's last name
