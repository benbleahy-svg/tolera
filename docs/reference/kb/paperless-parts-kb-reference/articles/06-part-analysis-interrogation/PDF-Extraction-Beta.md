---
title: "PDF Extraction Beta"
slug: PDF-Extraction-Beta
source: https://help.paperlessparts.com/s/article/PDF-Extraction-Beta
topic: "Part Analysis & Interrogation"
captured: 2026-06-19
---

# PDF Extraction Beta

> Source: https://help.paperlessparts.com/s/article/PDF-Extraction-Beta  
> Topic: Part Analysis & Interrogation

Paperless Parts' new AI-powered PDF extraction feature automatically extracts key part data quickly from digital (non-hand-written) PDF prints.

**Note: this feature is a limited beta test with experimental capabilities.** This feature is being made available to your shop very early so we can share what we're working on and collect your feedback. The capabilities outlined below will likely improve throughout the beta, but may work significantly differently when released widely to all customers. **To provide feedback or for any questions, please reach out to the Paperless Parts team member who introduced this feature to you.**

---

# How it works

This feature introduces **PartBot,**an AI-powered extraction engine that runs on any PDFs you upload to Paperless Parts. Whenever you upload a print to Paperless Parts (as a primary and/or supporting file), if it is a digital print, PartBot will scan the file and attempt to identify characteristics of the file and part, then **send you a chat message with its findings.**

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/649f0e64f39eb10e8e84bac0/file-7xIgD5RSfn.png)

## What it can extract

PartBot currently attempts to read prints and extracts file information and part metadata. The below table shows what PartBot will attempt to tell you about your files.

**Note: Artificial Intelligence is a powerful tool, but not remotely perfect or even as smart as a human.** **PartBot will attempt to extract the below fields and may often be correct, but as the human responsible for accurately quoting for your customers, you should always double-check what it says by looking at the print.** **See the below section on how PartBot can fail to learn more.**

| Attribute | How it works |
| --- | --- |
| Is the file a part drawing? | Based on the text layers of the PDF, PartBot classifies the file as a part drawing (likely containing part number, revision, description, and more) or not a part drawing. |
| Does the file contain CUI? | PartBot will report whether it detects keywords commonly associated with export controlled information, like "ITAR", "CUI", and "export controlled". |
| Drawing number | PartBot looks for strings of text near a label like "Drawing Number", "Dwg No.", etc. that is most likely to be the print’s drawing number. |
| Part number | PartBot looks for strings of text near a label like "Part No.", "Part Number", etc. that is most likely to be the part number. |
| Revision | PartBot looks for strings of text near a label like "Rev", "Revision", etc. that is most likely to be the drawing revision. |
| Description | PartBot looks like strings of text in the bottom-right quarter of the page that are likely to be the part title or description. It looks at factors like the position, font size, and words contained in the string. |
| Material | PartBot looks at all text in a document and determines whether the document is describing a part made out of one of the top global materials. The top materials include Aluminum 6061 (and several of its variations), A36, 304, 303, 4104, 316, 1018, and 403. |

## How accurate is PartBot / how can it fail?

PartBot can fail in many different ways:

- It can't read handwritten prints or digital prints without text layers.
- PartBot will not produce multiple values for prints containing multiple parts.
- 5% of the time, PartBot will incorrectly classify a PDF as a part drawing or not and will not attempt to extract information if it does not think it is a part drawing.
- When PartBot thinks a file is a part drawing, 35% of the time it will not extract the value of a particular field--like Part Number, Revision, Drawing number, etc--even if they are in the file.
- When PartBot has identified the value of a field, 15% of the time, it will be incorrect. However, the value it finds will never be made up; instead, it will sometimes find another word on the print that is not the relevant field.

## How can I provide feedback / how will this improve?

To provide feedback about PartBot, you can:

- Reply directly to PartBot in Paperless Parts' chat--we'll be looking at those replies.
- Fill out your part data with their correct information--we'll be tracking when you enter something different than what we predicted.
- Reach out to the Paperless Parts team member who introduced this feature to you.

As we get feedback on PartBot's performance, we will be both increasing its performance slowly over time and adding additional fields it can extract. **If you have specific suggestions of what would be value to extract, please reach out!**

---

# How will this work eventually?

Right now, PartBot extracts information to chat. Obviously, when this information is correct, this means you still need to copy-paste it into actual fields in Paperless Parts, which is still time-consuming.

Eventually, we hope to build PartBot's extractions into our normal file processing and plug PartBot's extractions directly into your part fields for you to carefully review, seeing not only the extracted value but where on the print it came from.

**If you have any feedback about how you would imagine PDF extraction working when fully integrated with Paperless Parts, please reach out!**
