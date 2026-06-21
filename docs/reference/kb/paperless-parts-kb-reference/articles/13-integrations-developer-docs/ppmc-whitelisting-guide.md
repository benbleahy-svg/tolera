---
title: "PPMC whitelisting guide"
slug: ppmc-whitelisting-guide
source: https://help.paperlessparts.com/s/article/ppmc-whitelisting-guide
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# PPMC whitelisting guide

> Source: https://help.paperlessparts.com/s/article/ppmc-whitelisting-guide  
> Topic: Integrations & Developer Docs

In order for the PPMC to properly communicate with our servers and receive updates it will need access to the following URLs over the following ports:

**Paperless Parts URLS**

- api.paperlessparts.com
  - Ports: 443
- app.paperlessparts.com
  - Ports: 443
- iot.paperlessparts.com
  - Ports: 50022, 51147

**Security and Package Updates**

- *us-west-2.amazonaws.com
  - Ports: 443
- us-gov-west-1.ec2.archive.ubuntu.com
  - Ports: 443, 80
- archive.canonical.com
  - Ports: 443, 80
- security.ubuntu.com
  - Ports: 443, 80
- artifacts.elastic.co
  - Ports: 443, 80

**Logging and Reporting**

- [d5649d9914424a06bfe208a8956b2025@sentry.io](mailto:d5649d9914424a06bfe208a8956b2025@sentry.io)
  - Ports: 443
- [https://s3-fips.us-gov-west-1.amazonaws.com](https://s3-fips.us-gov-west-1.amazonaws.com)
  - Ports: 443
