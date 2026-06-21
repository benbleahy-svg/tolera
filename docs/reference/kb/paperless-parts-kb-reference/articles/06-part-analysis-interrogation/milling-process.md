---
title: "Milling process"
slug: milling-process
source: https://help.paperlessparts.com/s/article/milling-process
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# Milling process

> Source: https://help.paperlessparts.com/s/article/milling-process  
> Topic: Part Analysis & Interrogation

Paperless Parts has an interrogation module for three-axis milling. This module analyzes a 3D part file and extracts useful attributes for pricing.

## Milling Overview

Other factors you should account for in pricing include the time it takes to program the part using a CAM package, any post processing steps, and the time and expense associated with packing and shipping the part. Each of these costs should correspond to its own operation.

To analyze a part for three-axis milling add this line to your pricing program:

mill3 = analyze_mill3()

The `mill3` object will contain the attributes described below.

| Attribute | Description | Units |
| --- | --- | --- |
| `setups` | P3LList copy of mill setups | n/a |
| `setup_count` | Count of mill setups | n/a |
| `features` | P3LList copy of all milling feature objects on the part | n/a |
| `feedback` | P3LList copy of all milling feedback objects on the part | n/a |

 Each item in mill3.setups contains the attributes described below.

| Attribute | Description | Units |
| --- | --- | --- |
| `setup_time` | Setup time (defaults to one hour) | hours |
| `runtime` | Mill runtime | hours |
| `confidence` | Confidence interval of the runtime estimate; value will be ‘High’, ‘Medium’, or ‘Low’ | n/a |
| `features` | P3LList copy of all milling feature objects that belong to the setup | n/a |
| `feedback` | P3LList copy of all milling feedback objects that belong to the setup |   |

### Per-Setup Operations

You can configure a process to create one or more operations for each detected CNC process. When configuring a CNC process, check the “per setup” box on each operation that you wish to be repeated for each setup. The per-setup operations will have access to all part information, not just the information related to one setup. Therefore, you must access the data corresponding to one particular setup. There is a global constant available to P3L to let you know which CNC setup corresponds to the current operation:

- INDEX – each per-setup operation will have this integer corresponding to a setup; numbering starts at 0, such that a part with three setups will have three operations whose INDEX values are 0, 1, and 2, respectively.

You would use this value, along with dynamic variables, to access the setup time and runtime of the current setup. See the per-setup example below.

## Examples

This example prices all milling setups as a single operation:

```
mill3 = analyze_mill3()
runtime = var('runtime', 0, 'Runtime, hr', number, frozen=False)
runtime.update(mill3.runtime)
runtime.freeze()
setup_time = var('setup_time', 0, 'Setup time, hr', number, frozen=False)
setup_time.update(mill3.setup_time)
setup_time.freeze()
machine_rate = var('machine_rate', 50, 'Machine Rate, $/hour', currency)
setup_rate = var('setup_rate', 75, 'Setup Rate, $/hour', currency)
PRICE = setup_rate * setup_time + machine_rate * runtime * part.qty
DAYS = 0

```

This example prices each milling setup as a per-setup operation:

```
mill3 = analyze_mill3()
runtime = var('runtime', 0, 'Runtime, hr', number, frozen=False)
setup = mill3.setups[INDEX]
runtime.update(setup.runtime)
runtime.freeze()
setup_time = var('setup_time', 00, 'Setup time, hr', number, frozen=False)
setup_time.update(setup.setup_time)
setup_time.freeze()
machine_rate = var('machine_rate', 50, 'Machine Rate, $/hour', currency)
setup_rate = var('setup_rate', 75, 'Setup Rate, $/hour', currency)
hours = setup_time + runtime * part.qty
PRICE = setup_rate * setup_time + machine_rate * runtime * part.qty
DAYS = 0

```
