---
title: "Integration manager"
slug: integration-manager
source: https://help.paperlessparts.com/s/article/integration-manager
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Integration manager

> Source: https://help.paperlessparts.com/s/article/integration-manager  
> Topic: Integrations & Developer Docs

Use an **Integration Manager** to get insight into any external software integrations that are connected to your Paperless Parts organization, as well as control the behavior of those integrations, all from within Paperless Parts.

#### On this page

- What is an Integration Manager?
- Integration Notifications
- API key location

---

# What is an Integration Manager?

Each integration that your organization has with an external software system will have its own Integration Manager, which you can access from the Integrations section of your organization's [settings](https://app.paperlessparts.com/settings/profile/info). From there, you can monitor an integration's behavior and prompt it to perform certain actions.

There are three entities that make up the Integration Manager:

- Integration Actions: A description of a capability of an integration.
  - Example integration actions include "Export Order" or "Import Contact".
- Integration Action Logs: A record of an integration's attempt to perform an integration action
  - Integration action logs display a timestamp, a status ("In Progress", "Completed", "Failed", etc), and other helpful information to help you understand what happened and why.
- Integration Action Requests: A request for the integration to perform a specific action.
  - Integration action requests can be initiated by you or a member of your team.

For the remainder of this article, let's consider an example integration with a fictional CRM system called CustomSoft.

![](/servlet/rtaImage?eid=ka0Ns0000009Ilh&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBsgf)

Clicking on the CustomSoft banner in Integrations settings will open the Integration Manager for our CustomSoft integration.

![](/servlet/rtaImage?eid=ka0Ns0000009Ilh&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBsn7)

The header section of the manager provides several important pieces of information. First, it states the last time an integration action log was updated. Second, it provides a status indicator that shows the last time the integration "phoned home" to Paperless Parts. Together, these indicators can be used to determine if the integration is operating properly.

Next, we can see the author and support contact for this integration. This fictional CustomSoft integration was developed by CustomSoft, and a support contact is labeled as user.com. For any integrations built by Paperless Parts, the author field will show Paperless Parts and clicking on the support contact will connect you directly to Paperless Parts Support.

Below the header are the integration action logs for this integration. Each integration action log indicates what type of action it is, which Paperless Parts record it references, the current status of the action, and the last updated timestamp. Clicking on the integration action record provides additional details, such as how the action was triggered and the status message.

![](/servlet/rtaImage?eid=ka0Ns0000009Ilh&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBsoj)

The Integration Manager also has a tab called "Request Actions". This tab allows users to issue integration action requests. In this example, users can trigger an Export Quote action, and select which Paperless Parts quote they would like to export. When an integration action is requested, a new integration action log record will be added with a "Queued" status, and a message will be sent to the integration to inform it of the new request.

![](/servlet/rtaImage?eid=ka0Ns0000009Ilh&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBsvB)

# Integration Notifications

Some integration failures are high priority and require immediate attention. You can configure Integration Actions to notify you within Paperless Parts if an action fails. Notifications allow you to respond quickly when an issue needs to be resolved, without having to constantly monitor the Integration Manager.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6440252137fd073d73d6cf9e/file-sqUi7f7BEd.png)For integrations authored by Paperless Parts, only integration actions that involve *exporting* data to another system will generate notifications by default. If you would like to receive notifications for other integration actions, please reach out to [our Support team](https://secure.helpscout.net/docs/64170b929146d549cd549658/article/632cc97ec5dd38351401ad50#). For custom integrations, please see the [Integration Development Guide](https://help.paperlessparts.com/s/article/integration-development-guide) for more information on how to configure integration notifications.

# API key location

To view the API key for any integration, select the relevant software from your Integrations page and click **Configure.**This will open the Integration Settings page for that specific integration.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/636983d4dfbb99158c1a15a5/file-6uIUSAqhRx.gif)

Access the API key in the **Connectivity**tab. Note that you must have Administrator privileges to view the API key.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6369844dae75b00b6be9487a/file-8lUcKzycpG.png)

#
