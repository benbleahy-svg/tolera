---
title: "Paperless Parts Managed Connector (PPMC) guide"
slug: paperless-parts-managed-connector-ppmc-guide
source: https://help.paperlessparts.com/s/article/paperless-parts-managed-connector-ppmc-guide
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Paperless Parts Managed Connector (PPMC) guide

> Source: https://help.paperlessparts.com/s/article/paperless-parts-managed-connector-ppmc-guide  
> Topic: Integrations & Developer Docs

### On this page

- What is a PPMC?
- Why do I need a PPMC?
- FAQ

# What is a PPMC?

The Paperless Parts Managed Connector (PPMC) is a small physical computer that gets installed on a shop's network to enable an integration to communicate between the Paperless Parts cloud-based API and an on-premises ERP system. The integration (sometimes called a connector) is a software application designed to move data between two systems. They are often customized for each shop but created from a standard integration with basic functionality. The PPMC enables our integration team to securely access the PPMC remotely to support the integration.

# Why do I need a PPMC?

An integration is a software application that moves data between Paperless Parts and a third-party tool, such as an ERP system. If the ERP system is on-premises (i.e., runs on servers physically located at a shop), then the integration has to run on a computer connected to that shop network. The PPMC is a standardized, inexpensive solution that solves two problems:

It provides a consistent environment to run our integration applications.

It enables our team to securely connect remotely, so we can deploy and support the integration.

# Frequently Asked Questions:

 Reach out to our support team with any additional questions that aren't answered here.

## What operating system does the PPMC run?

The PPMC uses Ubuntu a Linux-based operating system.

## Is port forwarding required for remote access?

No. The PPMC establishes a connection to our cloud that enables our team to securely manage the device and integration.

## Who is responsible for maintenance and updates of the PPMC?

The PPMC will perform regular software updates as they become available. Paperless Parts is responsible for this and maintenance of the PPMC.

## Can I install software on the PPMC?

No. The Paperless Parts team manages this device and all software installed on the device.

## What happens if the PPMC hardware fails?

We'll send you a new PPMC. The source code for any integrations running on your PPMC are securely archived in our cloud-based version control system. PPMCs don't store data about your parts, quotes, and orders; that information is stored in Paperless Parts and your other applications, such as your ERP system.

## How can a virtual PPMC be set up?

Customer to create Virtual Machine/Instance with the following requirements:

1. Ubuntu 22.04 LTS
2. 64+ GB of storage
3. 4+ CPU cores
4. 8+ GB of RAM/Memory

Customer to grant SSH access to Virtual Machine/Instance with root-level access.
