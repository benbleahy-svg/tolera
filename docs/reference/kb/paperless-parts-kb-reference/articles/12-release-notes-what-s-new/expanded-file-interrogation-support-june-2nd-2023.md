---
title: "Expanded file interrogation support - June 2nd, 2023"
slug: expanded-file-interrogation-support-june-2nd-2023
source: https://help.paperlessparts.com/s/article/expanded-file-interrogation-support-june-2nd-2023
topic: "Release Notes (What's New)"
captured: 2026-06-19
---

# Expanded file interrogation support - June 2nd, 2023

> Source: https://help.paperlessparts.com/s/article/expanded-file-interrogation-support-june-2nd-2023  
> Topic: Release Notes (What's New)

With this release, Paperless Parts can now interrogate and geometrically analyze:

- CAD files with simplify-able splines
- CAD files with non-solid-body issues
- IGES files

In order to geometrically analyze files that fall into these categories, CAD files with splines or gaps will be "healed" on upload - or slightly modified so that the file can be interpreted correctly. These geometry modifications are extremely minor and are equivalent to the changes any CAD file goes through when it is converted to a .STEP file, but we'll still alert you anytime they happen with a "Resolved error" warning: ![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6478efcf7360c921d3f9d0b5/file-eNZwzSJIHG.png)

Plus, when you download a file that's undergone "healing", you'll download the original version of the file without any modifications.
