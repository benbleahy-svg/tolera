---
title: "Paperless Parts Streaming API"
slug: paperless-parts-streaming-api
source: https://help.paperlessparts.com/s/article/paperless-parts-streaming-api
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Paperless Parts Streaming API

> Source: https://help.paperlessparts.com/s/article/paperless-parts-streaming-api  
> Topic: Integrations & Developer Docs

### On this page

- Introduction
- Event Streaming via Webhooks
  - Configuring a Webhook in Paperless Parts
  - Event Dispatches
  - Security Best Practices

---

## Introduction

Paperless Parts offers two APIs: the REST API and the Streaming API. With the REST API, the client initiates an interaction by sending an HTTPS request to the Paperless Parts API server, and the Paperless Parts API server sends the appropriate response back to the client. This is a standard model of interaction that should be familiar to any web developer. The REST API is well suited for use cases where the client wishes to ask questions about data in Paperless Parts or create, update, or delete data in Paperless Parts. However, the REST API is not well suited for use cases that involve responding to an event that has occurred in Paperless Parts. In order to detect that an event has occurred in Paperless Parts via the REST API, the client must implement a polling strategy, whereby the client periodically asks Paperless Parts if the event has occurred (typically on a regular interval). In order to be responsive, the client must reduce the polling interval. However, this is inherently inefficient because as the polling interval is reduced, the likelihood that an event occurred in any given interval diminishes. Polling strategies are also likely to encounter the rate limiting imposed by the REST API.

The Streaming API was developed to address use cases where the client needs to perform some action in response to an event occurring in Paperless Parts. In contrast to the REST API, in the case of the Streaming API the Paperless Parts API server initiates the interaction by sending a request to the client with the details of the event that occurred, and the client sends a response to the Paperless Parts API server to let it know it received the event details. This model allows the client to respond to events that occur in Paperless Parts in near real time, and also reduces web traffic by only sending requests when events have occurred, thereby making the Streaming API a much more responsive and efficient choice for these types of use cases.

## Event Streaming via Webhooks

A Webhook is the mechanism by which the Streaming API delivers events to the client. In order to receive events via the webhook, you will need to create a webhook endpoint in your client application. A webhook endpoint must be an HTTPS endpoint that is publicly accessible on the internet. Your webhook endpoint should return a response to the Paperless Parts API server immediately upon receipt of the event POST request - any business logic you perform on that event data should be done asynchronously.

### Configuring a Webhook in Paperless Parts

To configure a webhook, navigate to the Settings page and open the Integration Manager. From there, click "Configure" and select the Connectivity tab. Click "Create Webhook", and you will be brought to the webhook creation screen. Supply the URL of the webhook endpoint you created in your client application. Next, select the event types you want the webhook to publish to that URL. As of the writing of this guide, the available event types are:

- quote.created
- quote.status_changed
- quote.sent
- order.created
- order.status_changed
- integration_action.requested
- integration.turned_on
- integration.turned_off

![](/servlet/rtaImage?eid=ka0Ns0000009qx3&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBqrl)

### Event Dispatches

Once you have created the webhook, all of the events the webhook subscribes to will be dispatched to the webhook endpoint URL via an HTTPS POST request. Here is a sample POST body:

```
 {   "created": "2022-12-07T18:49:45.893180Z",   "data": {     "type": "bulk_import_contacts",     "uuid": "6c96b208-2cc9-4356-b6a1-f1ee9a8fb9b2",     "status": "requested",     "created": "2022-12-07T18:49:45.890275Z",     "updated": "2022-12-07T18:49:45.890298Z",     "entity_id": null,     "related_object": null,     "status_message": null,     "related_object_type": null   },   "object": "integration action",   "type": "integration_action.requested" }<br>
```

You can see a log of all the events that have been dispatched to your webhook on this screen. If you click on an individual event dispatch, you will see the POST body that was sent to your webhook endpoint, as well as the response your client application sent back. Logs can be sorted and filtered by name, response status code, and timestamp.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/63a3965d9cef114e6cd202bf/file-crZARTrqi5.png)

### Security Best Practices

Paperless Parts includes a signature in each event dispatch's Paperless-Parts-Signature header. This signature allows you to verify that the request was sent by Paperless Parts and not by a third party. To verify the signature, first get the webhook signing secret from the webhook configuration page.

![](/servlet/rtaImage?eid=ka0Ns0000009qx3&feoid=00N5G00000WB8Hk&refid=0EMNs00000RBqwb)

The Paperless-Parts-Signature header included with each event dispatch contains a timestamp and a signature. The timestamp is included when computing the signature to prevent replay attacks. The timestamp is prefixed by "t=", and the signature is prefixed by "v1", as shown in the example below:

```
 't=12345,v1=5f26f28df7e5c4a0f530a55fae5967cdad81915657a12e90aa0752c6ef9885a0'<br>
```

To verify the signature, perform the following steps:

1. Isolate the timestamp and signature from the Paperless-Parts-Signature header.
2. Create a new payload by concatenating:
  - The timestamp (as a string)
  - The character .
  - The JSON body of the POST request
3. Compute an HMAC signature with the SHA256 hash function. Use the webhook endpoints signing secret as the key, and use the concatenated payload from above as the message.
4. Compare the HMAC signature you computed with the signature provided in the Paperless-Parts-Signature header.

If the signatures do not match, you should reject the POST request.

See the Python code snippet below for an example of how to compute the HMAC signature:

```
 import binascii import hashlib import hmac import json   def create_hmac_signature(request_payload: dict, signing_secret: str, timestamp: int):     """ Generate a hash-based message authentication code using the SHA256 algorithm and the pre-shared secret 	key for this Webhook to allow the recipient to verify that the request was sent by Paperless Parts. """      payload_string = json.dumps(request_payload)     message = f'{timestamp}.{payload_string}'     message_bytes = (         message.encode()     )      signing_secret_bytes = binascii.unhexlify(signing_secret)      hmac_signature = hmac.new(         signing_secret_bytes, message_bytes, hashlib.sha256     ).hexdigest()      return hmac_signature<br>
```
