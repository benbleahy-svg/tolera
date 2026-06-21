---
title: "Viewer improvements - October 24th, 2022"
slug: viewer-improvements-october-24th-2022
source: https://help.paperlessparts.com/s/article/viewer-improvements-october-24th-2022
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Viewer improvements - October 24th, 2022

> Source: https://help.paperlessparts.com/s/article/viewer-improvements-october-24th-2022  
> Topic: Release Notes (What's New)

## Cube navigation

You now can navigate in the part viewer with a cube in the bottom left:

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/633cad2fcf38bc37aecf6869/file-jEzUAViPqv.gif)

This is meant to mimic the experience you would get with a desktop CAD software.

## Improved viewer loading with assemblies

We have optimized the way bodies load in the 3D viewer to make sure we load the most important stuff first. The impact will be felt the most when working with assemblies. You can now leverage opening the viewer in the child component view of the BAQ with much greater speed and utility. See the difference below. The new loading experience is on the left, the old one on the right.

## Increased file size support

We have made improvements to our server architecture, which will allow for faster processing of really large files during high loads. We have released the following:

- The 10MB file size limit for interrogation has been raised to 20MB
- Milling interrogations on very large files (5MB+) are ~25% faster
- Decreased latency (time spent waiting in the queue) by 25% for all customers across the board

Please reach out to support if you have any questions or feedback!

##
