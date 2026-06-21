---
title: "PPMC connectivity - next steps"
slug: ppmc-connectivity---next-steps
source: https://help.paperlessparts.com/s/article/ppmc-connectivity---next-steps
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# PPMC connectivity - next steps

> Source: https://help.paperlessparts.com/s/article/ppmc-connectivity---next-steps  
> Topic: Integrations & Developer Docs

Once shipment of the PPMC is confirmed by the Paperless Parts team, the next steps in the connectivity phase are to create credentials and provide information so that the Paperless Parts team is able to perform the following tasks:

- RDP to the SQL Server from our PPMC.
  - We RDP onto the SQL Server device in order to view and verify test orders as well as view the table structure of your SQL server databases.

- Write to and read from your production and sandbox SQL Server Databases.
  - Reading and writing from your SQL server databases is how we integrate with your ERP.

- Log in to your ERP instance to confirm and view orders.
  - This is valuable during the integration testing phase of the onboarding process to confirm the order has made it from Paperless Parts to your ERP.

Once the following steps are completed and the Paperless Parts team has verified the credentials we can consider the PPMC connectivity phase of the implementation complete:

*Note*: Please do not share credentials via email. Either securely send them, upload them into your Paperless Parts Parts library, or communicate them with the Paperless Parts team over the phone.

1. Create a domain account on your windows domain that allows for remote access (SSL VPN/RDP).
2. Create a test ERP database from a recent backup of your production database.
  1. Please make sure that the database is accessible from inside of the ERP application and that the Paperless provisioned user has access to it.
3. Create a username and password combination for SQL Server Authentication with read and write permissions on the test and production ERP databases.
4. Provide the versions of Windows Server and SQL Server.
  1. To check the Windows Server Version:
  2. To check the SQL Server version:
    1. Open SQL Server Management Studio. Look at the left panel entitled Object Explorer. The version number is shown in parentheses.
5. Provide the IP or hostname and port that the Microsoft SQL Server is running on:
  1. To find the hostname, click on SQL Server Services. The instance name/hostname is in parentheses in line with the SQL Server service.
  2. SQL Server runs by default on port 1433, but this is configurable. To determine which port SQL Server is running on, go into SQL Server Configuration Manager. Under the SQL Server Network Configuration tab, select Protocols for the instance name, then TCP/IP. Check to see if there are any port numbers other than 1433 listed (probably under TCP Dynamic Ports)
