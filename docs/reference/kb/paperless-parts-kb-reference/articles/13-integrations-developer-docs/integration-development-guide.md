---
title: "Integration development guide"
slug: integration-development-guide
source: https://help.paperlessparts.com/s/article/integration-development-guide
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Integration development guide

> Source: https://help.paperlessparts.com/s/article/integration-development-guide  
> Topic: Integrations & Developer Docs

### On this page

- Introduction
- Integration Setup
  - Create the Integration Manager
  - Create the Integration Action Definitions
  - Generate REST API Credentials
- Triggering Integration Behavior
  - Events
  - Integration Action Requests
- Integration Logging
- Integration Actions in Context
- Monitoring Integrations
- Integration Notifications
- Pause / Play Integrations
- Scheduling Integration Action Requests

---

## Introduction

Paperless Parts provides a Managed Integrations framework that allows integration developers to create powerful integration experiences for their users. The guiding principle behind this framework is the idea that a Paperless Parts user should be able to manage, monitor, and interact with their external software integrations seamlessly from within Paperless Parts. Empowering users to view integration behavior logs and request specific actions from within Paperless Parts greatly reduces communication overhead by giving these users the ability to answer most of their integration-related questions themselves, and also promotes efficient workflows by minimizing the need for users to jump between software systems to accomplish their daily work. Furthermore, building an integration that utilizes the Managed Integrations framework reduces the development burden on the integration developer by removing the need for the integration developer to create a separate user interface for the integration.

This article will provide a step-by-step walkthrough of the Managed Integrations framework and how it can be utilized most effectively by an integration developer looking to create a seamless experience for their users within Paperless Parts.

## Integration Setup

All of the steps in this section will require "Configure" permissions for Integrations - please reach out to the administrator of your Paperless Parts instance if you do not have sufficient permissions to access the screens depicted below. Please note that customer and third party development teams will not have access to the configure tab of Paperless Parts authored integrations, and note that you must have Administrator privileges to view the API key.

For illustrative purposes, in this article we will be using a recurring example of an integration with CustomSoft, a fictional custom-built CRM tool.

### Create the Integration Manager

The first step in setting up your integration is to create an Integration Manager record. The Integration Manager will house all of the configuration and logs for your integration, and will be the primary method by which users will interact with your integration from within Paperless Parts. To create an Integration Manager, navigate to the Settings page and click "Create Integration". If you do not see the "Create Integration" button, please have one of your Paperless Parts users reach out to Paperless Parts Support to inquire about increasing the allowed number of custom integrations.

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBr9V)

Once on the Create Integration screen, fill out the Software Name, Software Category, and Integration Description fields, and provide a logo image, if applicable. Then, fill out the Author and Support Contact fields. When filling out the Support Contact, please provide the email address of the best person for users to contact if there is a question about or issue with the integration (usually, but not always, this will be you as the integration developer). The user will be provided with a mailto link to the supplied email address, so it is important that the correct address is provided to ensure the best user experience.

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrJB)

### Create the Integration Action Definitions

An Integration Action Definition is a description of a capability of your integration. Suppose our example CustomSoft integration can do two things: export quotes from Paperless Parts to CustomSoft and import contacts from CustomSoft to Paperless Parts. The integration would need two corresponding Integration Action Definitions: "Export Quote" and "Import Contact". All log statements and action requests need to be tied to an Integration Action Definition (more on these concepts in subsequent sections), so you will need to create an Integration Action Definition for each discrete piece of logic in your integration that you want to report on or allow users to trigger manually.

To create an Integration Action Definition:

1. Click on the Integration Manager you created in the previous step
2. Click the Configure button
3. Click Add Action Definition

First, fill out the Type, Display Title, and Display Description fields. Next, fill out the Has Paperless Parts Entity checkbox. Note that if the action you are defining is tied to a Paperless Parts entity, the user will be provided with a selector that allows them to quickly pick the appropriate entity when requesting an action of that type. In this example, we are defining an action called "Export Quote" and we want the user to be able to easily indicate which Paperless Parts Quote to export - see the screenshot below. Defining the Paperless Parts entity will also allow the user to filter logs by type, and will dictate which screens in the application the user will be able to access their integration manager from. In this example, since this action is defined for Quotes, the user will be able to access the integration manager functionality for this action while editing a specific quote (more on this later). After optionally indicating which Paperless Parts entity type this action should be tied to, indicate whether or not this action can be requested. If you only want to display logs for this action but do not want to give the user the option to request this action manually, leave this box unchecked. Note that this checkbox only controls the user interface that is presented to the user in Paperless Parts - it will be up to you as the integration developer to ensure that your integration is capable of receiving and acting upon action requests. We will cover action requests and the Paperless Parts API in a subsequent section of this article.

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrO1)

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrPd)

### Generate REST API Credentials

In order to read data from and write data to Paperless Parts, your integration will need a valid REST API Token. The REST API Token can be managed from the Connectivity tab in the Integration Manager. Only the team admin for your Paperless Parts will be able to manage the REST API Token for your integration. Please reach out to your team admin if you cannot view the API Token on the Connectivity tab.

## Triggering Integration Behavior

Most integrations perform actions in response to some event occurring, whether in Paperless Parts or in an external system. This section describes how to listen for events from Paperless Parts. Note that while Paperless Parts generates events and makes them available to consume via our API, it is the responsibility of the integration developer to write the integration in such a way that it can perform actions in response to events being generated.

### Events

Events are facts about things that have happened in Paperless Parts, which are generated automatically by Paperless Parts. Example events include "order.created" and "quote.sent". The full list of events generated by Paperless Parts will expand over time. As of the writing of this guide, the available event types are:

- quote.created
- quote.status_changed
- quote.sent
- order.created
- order.status_changed
- integration_action.requested
- integration.turned_on
- integration.turned_off

Events can be delivered to your integration service via a webhook as part of Paperless Parts' Streaming API. With a webhook configured, Paperless Parts will dispatch events as soon as they occur by sending an HTTPS POST request to the URL you supply. Using a webhook, you can create responsive integrations that are triggered in near real time by events that occur in Paperless Parts. For more information on how to configure a webhook in Paperless Parts, please see [this article](https://help.paperlessparts.com/s/article/paperless-parts-streaming-api).

If the use of a webhook is not an option, events can also be retrieved via a polling strategy by using [the Events list API endpoint](https://docs.paperlessparts.com/#Events). This endpoint allows you to filter by event type, so you can be very specific about which events your integration responds to. When an event is first retrieved via the API, it is marked as having been "dispatched". This is conceptually similar to marking an email as read. You can filter the events list endpoint to only return events that have not yet been dispatched. In this way, your integration can periodically poll for new events, and only receive events that have been generated since the last polling request was sent.

### Integration Action Requests

In contrast to Events, which are generated automatically by Paperless Parts, Integration Action Requests are manually generated by users. An Integration Action Request can only be issued for an Integration Action Definition where the "Can be requested" checkbox is selected.

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrSr)

For the purposes of the API, an Integration Action Request is just a special kind of event, with type "integration_action.requested". You can fetch these events in the same way you would any other type of event, using the events list endpoint.

## Integration Logging

One of the primary benefits of the Managed Integrations framework to the integration developer is that it provides a user interface for the end user to view integration logs inside Paperless Parts. This likely will not replace the need for the developer to implement their own logging solution for developer-facing logs. However, it gives the end user visibility into the workings of the integration and serves as an audit log of whether records were processed as expected. The Managed Integrations framework provides a mechanism for storing and visualizing integration logs, but it is up to you, the integration developer, to populate them from your integration software.

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrUT)

An Integration Action is a log record of an integration's attempt to perform a specific action, including the current status of that attempt, and the timestamp of the last update. The allowed statuses are: "queued", "in_progress", "completed", "failed", "cancelled", and "timed_out". All Integration Action records must be tied to an Integration Action Definition. As such, you will need to create an Integration Action Definition as described in the "Integration Setup" section above before you can display any integration logs to the user.

Integration Actions can be created and updated via the Paperless Parts REST API (see the API documentation [here](https://docs.paperlessparts.com/#Integration%20Actions)). A typical integration would respond to some event trigger, as described in the previous section, and immediately create an Integration Action record in the "queued" status to give the user visual feedback that the integration is aware that it needs to perform an action. Once the handling of that action is underway, the integration should update the Integration Action record with the status "in_progress". Once the action has either succeeded or failed, the integration should update the Integration Action record with status "completed", "failed", "cancelled", or "timed_out". Note that a status message can be included when updating an Integration Action. This is intended as a way to give the user more context about the action. It is best practice to include a human-readable status message, rather than simply copying in an error message from an uncaught exception or something similar. Also note that expanding the details for an Integration Action allows the user to quickly contact whoever was listed as the support contact when creating the Managed Integration. Note that as of this writing, the status message will only be displayed for "completed" and "cancelled" Integration Action logs.

When an integration action is manually requested from within Paperless Parts via an Integration Action Request, a corresponding Integration Action record is created automatically in the "queued" state. This removes the need for the integration to create the Integration Action record itself, in this situation. Automating this step provides a better experience for the end user because it gives them immediate visual feedback that their action request has actually happened, which should discourage them from making duplicate requests for the same action. As described above, Integration Action Requests will be delivered in the form of events with type "integration_action.requested". When responding to events of that type, your integration need only be concerned with updating the existing Integration Action record referenced in the payload of the event.

## Integration Actions in Context

Up to this point, we've focused on managing an integration from the Settings page. One of the key benefits of the Managed Integrations framework is that it also allows the user to Integration Action logs and request actions from within context in various other areas of Paperless Parts. In our example integration, we have an Integration Action Definition called "Export Quote" which is defined for the Paperless Parts entity "Quotes". If a user were editing a quote, they would be able to access the integration manager by clicking the "Actions" button and navigating to the integration in the "Relevant Integrations" section. Upon opening the integration manager, the user would be able to request any of the appropriate actions for this quote (only those actions with a Paperless Parts entity of "Quotes"), and would additionally be able to view logs for previous integration actions related to this quote. This allows users to interact with the integration from the areas of the application where they already spend the majority of their time, which in turn makes the integration feel like a tightly coupled and integral part of the user's workflow. As of this writing, the only integration actions that can be triggered from within context are integration actions tied to Quotes.

## Monitoring Integrations

The Managed Integrations framework provides a mechanism for integrations to report on their current status. This takes the form of a health indicator which indicates the last time the integration reported its status. The purpose of this health indicator is to give the user confidence that if they request an action or generate an event that should trigger an action, the integration will be ready to receive that action request or event and perform the action. It is up to you as the integration developer whether you wish to implement these status reports. If you scroll up and look at the screenshot for the Create Integration screen, you'll notice a checkbox that says "Show status indicator". You will need to check this box in order for the indicator to be displayed to the user. It is a best practice to report the status of the integration frequently (on the order of every 5 minutes) to give the user timely feedback in the event that the integration is experiencing downtime. Please see the "Post an integration heartbeat" endpoint in the [API documentation](https://docs.paperlessparts.com/#Integration%20Actions) for more information on how to report your integration's status.

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBre9)

## Integration Notifications

The Managed Integrations framework provides a mechanism for generating in-app notifications for your users when an integration action fails. Specifically, a notification will be generated for each user where the following conditions are met:

- The Integration Action Definition is configured to "notify on failure"
- The user has "View logs" permissions for Integrations, or higher
- An integration action log record is updated with a status of "failed", "cancelled", or "timed_out"

The resulting in-app notification will include the name of the Integration Action that failed, as well as the related object that integration action references (i.e. the Order or Quote), if applicable.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6440252137fd073d73d6cf9e/file-sqUi7f7BEd.png)

## Pause / Play Integrations

The Managed Integrations framework provides a mechanism for users to pause / play their integrations. This takes the form of an action in the Actions dropdown on the Integration Manager. The purpose of the pause / play action is to allow users to temporarily disable the integration. As with the rest of the Managed Integrations framework, it is up to you as the developer to make sure your integration is capable of receiving pause / play instructions. These instructions will be delivered as events with types "integration.turned_on" and "integration.turned_off".

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrfl)

## Scheduling Integration Action Requests

In certain situations, it is helpful to be able to schedule Integration Action Requests instead of kicking them off manually. To do this, navigate to the Automation tab in the Integration Manager settings page. For illustrative purposes, I've defined a third integration action called "Bulk Import Contacts" that will be scheduled to run once per day, as shown in the screenshots below:

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBqlK)

![](/servlet/rtaImage?eid=ka0Ns0000009Hcj&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBrhN)

Note that only integration action definitions which do not have an associated Paperless Parts entity can be scheduled. The reason for this is that scheduled action requests do not provide an opportunity for the user to supply input information, and as such a Paperless Parts entity (a Quote, Order, etc) can not be selected at the time the action request is generated.
