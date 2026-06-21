---
title: "Autodesk Fusion Integration"
slug: autodesk-fusion-integration
source: https://help.paperlessparts.com/s/article/autodesk-fusion-integration
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Autodesk Fusion Integration

> Source: https://help.paperlessparts.com/s/article/autodesk-fusion-integration  
> Topic: Integrations & Developer Docs

Paperless Parts' new Autodesk Fusion integration allows you to move files back-and-forth between systems for file healing, improving manufacturability, or preparing toolpaths.

---

## How it works

This integration allows you to move files back-and-forth between Paperless Parts and Autodesk Fusion right from the part viewer.

### Browsing hubs, projects, folders, and files

After opening the ecosystem app in the viewer, you can browse hubs, projects, folders, and files just as you would in Fusion.

Use the breadcrumb at the top to step backwards, or click the leftmost icon to switch hubs.

![](/servlet/rtaImage?eid=ka0Ns0000004huP&feoid=00N5G00000WB8Hk&refid=0EMNs00000Cj7Xw)

### Exporting files to Fusion

To send files to a particular folder in Fusion, navigate to that folder, select “export files here”, then “export” from the popup menu.To send an assembly file, make sure to select the root part from the BOM tree view first; while to send a file attached to an assembly subcomponent, make sure to select that component first.

![](/servlet/rtaImage?eid=ka0Ns0000004huP&feoid=00N5G00000WB8Hk&refid=0EMNs00000CimDK)

### Importing files from Fusion

To import files to the current part from Fusion, navigate to that file, mouse over its row, and click “import”, which will bring the file in as a supporting file of the part/component selected in the BOM tree.

This may take up to a minute to complete, as Fusion may need to convert the file to an appropriate format first.

![](/servlet/rtaImage?eid=ka0Ns0000004huP&feoid=00N5G00000WB8Hk&refid=0EMNs00000CjBoQ)

---

## Getting started

This integration streamlines connecting both systems by having a single admin log in to Autodesk once, which grants all Paperless Parts users with “request actions” integration permissions to use the integration indefinitely.

### Pre-requisites

To set up and use this integration, you’ll need:

- An account with Autodesk Fusion
- “Configure” integrations permissions within Paperless Parts

### Instructions

1. Visit the [integration settings page](https://app.paperlessparts.com/settings/integrations/quickbooks)
2. Click “Connect” next to Fusion Teams, then “Continue to Autodesk”.    ![](/servlet/rtaImage?eid=ka0Ns0000004huP&feoid=00N5G00000WB8Hk&refid=0EMNs00000BlZVR)
3. Sign into Autodesk, authorizing the integration to view and manage your data. See the [FAQ](#faq) for more information about how Paperless Parts uses this access.    ![](/servlet/rtaImage?eid=ka0Ns0000004huP&feoid=00N5G00000WB8Hk&refid=0EMNs00000BlXiA)
4. Once complete, head to the viewer for any part and open the ecosystem app, where you’ll now be able to browse your A360 hubs, projects, files and folders as well as import/export files.

      ![](/servlet/rtaImage?eid=ka0Ns0000004huP&feoid=00N5G00000WB8Hk&refid=0EMNs00000Bla9l)

---

## FAQ

### What access does Paperless Parts need for your Fusion data and how is it used?

In order to enable this integration, Paperless Parts needs the ability to both read and write to your A360 hubs and projects. Paperless Parts will only be able to access information that the person who set up the integration / signed in could access.

Paperless Parts uses this access only to enable your team--never reading data or transferring files without your team initiating it in our application. No data from Fusion is permanently stored within Paperless Parts unless it is imported.

### Once it’s set up, who can use the integration and what can it do?

When enabled, all users in your account with “request actions” integration permission will be able to:

- Navigate all hubs, projects, and folders [that the person who signed in] has access to
- Export non-export-controlled files to Fusion
- Import files from Fusion

### Why can’t I send export-controlled (ITAR/CUI) files to Fusion?

Autodesk Fusion is a non-compliant system, meaning sending export-controlled information would violate U.S. regulations.

To prevent doing this accidentally, Paperless Parts blocks you from sending files entirely when a part is marked export-controlled and warns you to verify files are not export-controlled every time you send them.

### How can I disconnect / sign out of the integration?

Contact the Paperless Parts support team, who can disconnect it for you; or have your admin revoke your API approval on the Fusion side.
