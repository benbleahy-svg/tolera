---
title: "What is Paperless Parts Pricing Language (P3L)?"
slug: what-is-paperless-parts-pricing-language-p3l
source: https://help.paperlessparts.com/s/article/what-is-paperless-parts-pricing-language-p3l
topic: "Pricing, Costing & P3L"
captured: 2026-06-19
---

# What is Paperless Parts Pricing Language (P3L)?

> Source: https://help.paperlessparts.com/s/article/what-is-paperless-parts-pricing-language-p3l  
> Topic: Pricing, Costing & P3L

Paperless Parts created P3L, a mini-language based on [Python 3](https://www.python.org/), to make it very easy to express your pricing with a small amount of code. P3L extends Python by adding global objects and functions and removes some other Python functionality for security and performance.

We have developed P3L to be very easy to learn and use for users comfortable with spreadsheets. You do not need to have experience in software development to be able to write or customize a P3L pricing program. Please contact our [support team](mailto:support%40paperlessparts.com) for help customizing your pricing.

## Processes and Operations Overview

The Paperless Parts platform centers on quotes. Quotes contain quote items, quote items contain one or more components, and components are parts you will manufacture (or assemble or purchase, e.g. hardware). Each component is manufactured using a single process. Some shops offer one process, while others may offer many different processes. The process determines which steps a part must go through before a shop can deliver a finished product. In Paperless Parts, each step of this process is called an operation. *The responsibility of a process is to generate operations on a part*. P3L runs at the operation level to estimate the cost and lead time required to perform that operation for a particular quantity.

The inputs to a P3L program are the part specification, including quantity, as well as any shop or process-specific variables, like labor rate, machine rate, and so on. The output of a P3L program is the price (in dollars) and lead time (in business days) required to produce the specified quantity of part.

When pricing a component with multiple operations and quantities, a P3L program will be executed for each operation and for each quantity. The outputs of the operations then sum across the component. If the quote item has more than one component (for assembly files), the totals will then sum across all components associated with a quote item.

## Pricing Theory

The operations interface was built on the fundamental idea that pricing is driven by two primary values: `setup_time` and `runtime`. Most operations will have a `setup_time` and a `runtime`. A `setup_time` is multiplied by a rate (dollars per hour) to get a setup cost. A `runtime` is multiplied by the make quantity and a rate (dollars per hour) to get a runtime cost. In other words, a `setup_time` is a one-time investment per operation, while `runtime` is a per-quantity investment per operation. At its simplest, the pricing output of an operation for typical operations (like programming or a milling operation) will be

```
 PRICE = setup_time * hourly_rate + runtime * make_quantity * hourly_rate
```

This basic setup time/runtime concept is reflected very strongly in our user interface, seen below:

### ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/5d35bf682c7d3a2ec4bf3c44/file-w7EFyv8Few.png)

# Process Level P3L

P3L can also be used in a custom process to generate operations and even set custom attributes on the part and in generated operations. Process level P3L is very similar to operation level P3L (described above). It has access to most of the same functionality. More details can be found [here](https://help.paperlessparts.com/s/article/custom-operation-generation).

# Add On Level P3L

Add ons are operation-like items that you can add to quote items that can influence total line item cost without influencing the unit price of a component. Things like non-recurring engineering work or tooling fees can be encapsulated by required add ons, where the buyer must purchase these alongside any quantity of a line item. Things like additional value added services or certifications can be encapsulated using non-required add ons that the user can optionally select at checkout if he or she finds it valuable. Add ons can be templatized in a very similar way to operations. Add on level P3L is very similar to operation level P3L, except it has access to a slightly different list of functions.
