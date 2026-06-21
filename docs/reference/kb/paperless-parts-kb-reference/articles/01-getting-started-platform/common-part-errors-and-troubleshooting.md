---
title: "Common part errors and troubleshooting"
slug: common-part-errors-and-troubleshooting
source: https://help.paperlessparts.com/s/article/common-part-errors-and-troubleshooting
topic: "Getting Started & Platform"
captured: 2026-06-19
---

# Common part errors and troubleshooting

> Source: https://help.paperlessparts.com/s/article/common-part-errors-and-troubleshooting  
> Topic: Getting Started & Platform

Learn why certain files may be unable to display and how you can resolve common upload errors.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/640f772ddc01bb231eb3c3be/file-cCMeTMGC7Y.png)

**On this page**

- Unsupported file types
- Zero-byte files
- Exporting assembly files incorrectly

---

# Unsupported file types

Although you can upload a wide array of file types in Paperless Parts, not all file types are viewable. If a file is unable to display in your account, check that it is a supported file type [here](https://help.paperlessparts.com/s/article/supported-file-types).

# Zero-byte files

If a part is unable to load or display in Paperless Parts, one common culprit is that it does not have any data associated with it. These are called zero-byte files.

### How do I check if a file has zero bytes?

To confirm that you have a zero-byte file on your hands, locate the file in your system's Finder and check the size. Usually, a file will have at least a few bytes of data.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6421df7a5d17363e673bdb2a/file-9S2KR1Saet.png)

There are a few common ways you can end up with a zero-byte file:

- You dragged and dropped the file directly into Paperless Parts from an email.
  - Zero-byte files can occur when file transfers do not complete successfully.
  - If this is the case, try downloading the file locally from the email before uploading it into your account.
- You may have received an archived email from your buyer or some other external party.
  - Not every attachment makes it through all of the file transformations and tools that are used (e.g. archiving and exporting of email accounts, conversion of email formats, culling of emails, etc.).
- Your operating system cannot handle the file's properties.
  - There are limits to a file's metadata (i.e. the data about the file like its name, when it was created, etc.) Some Windows operating systems have issues with extremely long file and folder names.
  - Even if your buyer can open a certain file on their system, when they send it to you it may be downloaded to a folder with a long name. This can potentially cause the file to incorrectly save on your system and become corrupted.
- The file was intentionally created without any data as a placeholder.
  - Sometimes zero-byte files may be created on purpose, just to provide extra information in a folder. For example, a file named __PLACEHOLDER__ may have no data associated with it.

# Exporting assembly files incorrectly

Although we support SLDASM / ASM / Catproduct / IAM files, these file types are only assembly instruction manuals to SLDPRTs / PRTs / Catparts / IPTs. Information about assembly components and their geometry is actually stored in the latter files. *Both* are needed to construct the entire part in Paperless Parts, and uploading one without the other will produce an "Unable to display" error.

To ensure that the assembly part loads correctly, export the associated files from SolidWorks, PTC Creo, Catia, or Inventor into a ZIP file using **Pack-and-go** (or an equivalent action). Instructions on how to export and upload assemblies correctly can be found [here](https://help.paperlessparts.com/s/article/supported-file-types#pack-n-go).

If your assembly file still is not loading correctly, it's possible that it is over our current file size limit (150 MB).

#### If your part is still not displaying correctly, reach out to [our Support team](#) for additional help.
