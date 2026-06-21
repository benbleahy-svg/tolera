---
title: "3D viewing limits"
slug: 3D-viewing-limits
source: https://help.paperlessparts.com/s/article/3D-viewing-limits
topic: "Part Viewer (3D / PDF / Models)"
captured: 2026-06-19
---

# 3D viewing limits

> Source: https://help.paperlessparts.com/s/article/3D-viewing-limits  
> Topic: Part Viewer (3D / PDF / Models)

Paperless Parts supports uploading and viewing CAD files up to 250mb in size. Within these files, Paperless Parts' 3D viewer can support rendering up to 25 million internal [vertices](https://en.wikipedia.org/wiki/Triangle_mesh) (that make up faces and edges visible in models) concurrently--and implements bounding-box-based **simplified representations**when one or more bodies exceed that limit.

### When a collection of bodies exceed the render limit

When attempting to view multiple bodies that collectively exceed render limits, Paperless Parts will replace some 3D bodies with bounding-box-based **blue simplified representations,** prioritizing the smallest and most insignificant bodies necessary to understand the collection of bodies' geometry. You can see which bodies are hidden this way by looking for **blue****cube icons** in the BOM and CAD tree.

These simplified representations are temporary, and based on how many bodies you are attempting to view at once. To view a specific body or subset of bodies, you can isolate a subassembly or that specific part in the BOM or CAD tree; since this action will reduce the bodies you are attempting to view, you’ll likely restore some or all previously hidden-parts.

![](/servlet/rtaImage?eid=ka0Ns0000001Dcj&feoid=00N5G00000WB8Hk&refid=0EMNs000000yBYU)

### When a single body exceeds the render limit

Rarely, a single body in a particularly complex CAD file will exceed Paperless Parts' rendering limits all on its own; when this happens, Paperless Parts will replace it with a single bounding-box-based **orange simplified representation.** You can see which bodies are hidden this way by looking for **orange** **cube** **icons** in the BOM and CAD tree.

Parts that exceed this render limit are also likely to exceed [Paperless Parts' interrogation limits](https://help.paperlessparts.com/s/article/interrogations-basics), and will not be able to display interrogation feature results in the viewer.

![](/servlet/rtaImage?eid=ka0Ns0000001Dcj&feoid=00N5G00000WB8Hk&refid=0EMNs000000yesD)
