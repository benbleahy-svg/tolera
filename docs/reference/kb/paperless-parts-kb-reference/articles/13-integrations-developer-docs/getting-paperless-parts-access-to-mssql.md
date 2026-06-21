---
title: "Getting Paperless Parts access to MSSQL"
slug: getting-paperless-parts-access-to-mssql
source: https://help.paperlessparts.com/s/article/getting-paperless-parts-access-to-mssql
topic: "Integrations & Developer Docs"
captured: 2026-06-19
---

# Getting Paperless Parts access to MSSQL

> Source: https://help.paperlessparts.com/s/article/getting-paperless-parts-access-to-mssql  
> Topic: Integrations & Developer Docs

# *Providing Paperless Parts MSSQL Access*

> *This document provides instructions to obtain the appropriate SQL database credentials necessary to configure your Paperless Parts integration. This document is intended for SQL server hosted on a Windows-based OS.*

We will need a 'Login' which is tied to a 'User' for each database we need access to. Those users will need Read and Write permissions to the respective databases. An account with admin rights will be needed to create access Login/Users for the Paperless Parts PPMC. In the end, Paperless Parts will need the information list below for connecting remotely to the MS-SQL Server (SQL Server):

- Username
- Password
- Host address (IP address or DNS resolvable domain)
- Port
- Database name(s)
- Instance name

**Are you configuring the Integration Connector windows application?** This information can be entered directly into the Integration Connector. Alternatively, this information is to be delivered to your Paperless Parts contact.

## What is the Instance Name?

This is the name of the SQL Server instance running the database(s) for the ERP system we want to link Paperless Parts to. The login screen for SQL Server Management Studio will show the <computerName>\<**InstanceName**> as Server Name. If your instance is not listed in the drop-down for Server Name you can use the "Browse for more..." option to find other available "Instance names".

![](https://lh4.googleusercontent.com/njRmMPwDGRcpaVih4-gyGdr7FqP4brVZ4dZ4OgPGLp72T8s8sK5IR37IATq8CF7fp2GwGn_LsHe3xMgRT853EjxAsaUrlkMnrpuiSVq_2pNIgOfyYTSejnhJ8m7wT4IwTL6OFmlKaiS9mC69pw21fg)

## What is the Database Name?

Inside SQL Server Management Studio, in the Object Explorer, expand the Databases folder. The objects with the cylindrical icons are the databases with the name listed next to each icon.

![](https://lh6.googleusercontent.com/aTNDZO_ge4A26Eltai5Zou0l7hI4ctBiiRjnNRuY9bbnObX-NEXy2oszWkR9_O7wp2oTJfwAEanHkBvYEzDRPN7FsZL1x7c9xfqriDoVdpP-LImZpOzWFOS33k5bf7_U6EYN9d41x4XcOJ_utIOPSA)

## How to create a new login in SQL Server with SQL Server Management Studio

**Step 1)** Create a login for the SQL server.

1. Connect to SQL Server then expand the Databases folder from the Object Explorer.
2. Navigate to Security > Logins the SQL Server host the database(s) in question by expanding the explorer tree
3. Right-click the Login folder and select "New Login…"

![](https://lh4.googleusercontent.com/6SE2VWJP0LafTwL6lrqrViIc-cE8z5FVL0rCS8nlmfcEcq2jRZo4XD-kMwnmwzrWcb48OXKHVf7EzbG8vC24DfUW6EM3CEekoimJnJkv6aaNBf0OO0lo9A-3yjhFmoqgRztBSeKZ3v4sBHngfLrMEQ)

**Step 2)**On the next screen, enter:

1. Login Name

2. Select SQL Server authentication

3. Enter Password for the user to be created

4. Make sure "Enforce password expiration" and "User must change password at next login" are **not checked off**.

5. Click Ok

![](https://lh3.googleusercontent.com/sNWvYWwYDFjqkJO0EsOKxSdAIyeEMbfO54ZS_mKdGfmlvvhzAvTDzdk00RcSWmOZGOHGPOS1A2uv2IfIlAimkWiOcYS_dyKzMHEYNlOK6pFqlNJvNA5zgazIqmM_YamUnrRUtE_kjZWfgGZyjaldgQ)

**Step 3)**The Login is created and can be seen under the Login folder.

![](https://lh3.googleusercontent.com/5azxzasBsQAHK3zOWOirWknWK937yYXnzjgIlNqqFgn7ji-U74KfMI8hp-wvw6y0e4TmYO4PgpEgCWrNg8dBq0ju_K6njkSiaSA1Exnx6f7fTbz3jQBjzpRupIY_7H8A_i8kkK-6FH1rsTVT_jYYPQ)

You can also create a login using the T-SQL command for SQL server create login and user.

```
 USE Master CREATE LOGIN <user-name> WITH PASSWORD = <strong password>;
```

Example:

```
 USE  Master CREATE LOGIN paperless WITH PASSWORD = <strong password>;
```

## How to create a user

A user is an account that you can use to access the SQL server. To create SQL server users, you can use:

- SQL Server Management Studio
- T-SQL

### How to create a user in SQL Server Management Studio

Here is a step-by-step process on how to create a user for the target database in SQL Server Management Studio:

**Step 1)** Connect to SQL server to create a new user.

1. Connect to SQL Server and expand the Databases folder from the Object Explorer.
2. Identify the database for which you need to create the user and expand it.
3. Expand its Security folder.
4. Right-click the Users folder then choose "New User…"

**Step 2)**Enter User details.

![](https://lh5.googleusercontent.com/VfBvGmTSD_44LJRVyGcERWkZbK0SBg8GPBw8hz5qCdj63s4Qu6ZrW_MstE-ALQOOFE560WFaj1gINqhUWzXhs9S0-LvK_Fzar84_ExaEcd1i-JjV7yMfy6rfxaGUzhBycvHXYGUUUtNJQvbc48nCzA)

You will get the following screen:

1. Enter desired User name

2. Enter the Login name (created earlier)

3. Click OK

![](https://lh3.googleusercontent.com/rBtxqeNgvcF25QfP6eCwOD7g5NYf2PZD3BBXIlC9-rEEpUQfjXLItJu9McpxfcQzIibq-6xvwpREvuFU-l9AWJFRxcqYHvaQ4VQnB71WDMxI15CXydQ5NEWZGurYnN8br-LHYW-Zo-2rIMIbxsuutw)

**Step 3)** User will be created

The new user that was created should be visible an element under the expanded User folder.

![](https://lh4.googleusercontent.com/R7rJ2buVe239KPOFIsIVBgHwRCg__B1O0_Mtp9sYUyRbZZPgDqoVyhamsDAJT9sbGM0BmCqbHdfN65uDjVQ-UR8ajWTA9iXIh6qF6puhnpNGNdfnlIhtTUNJiXn5gMchKr8RPWuid7fZTTsxMIdMGQ)

### Create user using T-SQL

You can use the T-SQL's create user command for the SQL server to add a user to the database. The SQL create user command takes the following syntax:

```
 USE <database-name>  CREATE USER <user-name> FOR LOGIN <login-name>
```

Example:

```
 USE PaperlessPartsVET  CREATE USER paperless FOR LOGIN paperless
```

*N**ote*: The query should be executed within the query window. If a user is already created for a Login, SQL Server will throw an error if you create a user for the same login.

## Assigning Roles to a User in SQL Server

Roles refer to sets of rules that govern the levels of access that users have to a SQL Server database. MS SQL allows you to grant, revoke and deny such roles. There are two ways to give SQL server user roles:

- Using SQL Server Management Studio
- Using T-SQL

### Granting Roles in SQL Server Management Studio

Here is a step-by-step process on how to assign roles to a user in SQL server management studio.

**Step 1)** Connect to your SQL Server instance and expand the folders from the Object Explorer as shown below. Right-click on the name of the user for the database in question then choose Properties.

![](https://lh4.googleusercontent.com/FiqTnJwYXeC0CDhpfFH3lPdq9mlxG-4WYu4g5jFgOcZCbEYVjgeB7tp61Bg-3c_38EY4wBVD1M-ioZKEnm5DBUbu0BDTSfbWjuHePVRgKlUhwMWIKRGShGSz-q0CW9xUXcslKw7Mb08fei27vtYCSw)

**Step 2)** In the next screen:

1. Click the Membership option from the left.

2. Select the checkboxes for all roles except for 'db_denydatareader' and 'db_denydatawriter'.

3. Click OK

![](https://lh4.googleusercontent.com/W8bImv1lLDWtfpnDiZ-LFunybe2XiE70NhPvwMu4fL9qJXldYBvo-xi3gBnZVCg8WtX-yJ29UAq4P7PY9d71b_hDaVnhtEezJhp3_gl1bPRuBco6z6C8FZwxQ2l_YBX5gy_2fxr6ECA_kjyxs4B4EA)

### Granting Roles using T-SQL

To grant roles to a user using T-SQL, you first select the database using the use statement. You then assign each role to the user using the "ALTER ROLE" statements. Here is the SQL Server syntax for adding users to a role:

```
 USE <database-name>  ALTER ROLE <role_name> ADD MEMBER <user_name>
```

For example, the following commands show how you can grant roles to a user named paperless for a database named PaperlessPartsVET:

```
 USE PaperlessPartsVET  GO  ALTER ROLE db_accessadmin ADD MEMBER paperless  ALTER ROLE db_backupoperator ADD MEMBER paperless  ALTER ROLE db_datareader ADD MEMBER paperless  ALTER ROLE db_datawriter ADD MEMBER paperless  ALTER ROLE db_ddladmin ADD MEMBER paperless  ALTER ROLE db_owner ADD MEMBER paperless  ALTER ROLE db_securityadmin ADD MEMBER paperless  GO
```

## Find Ip Address:

1. Press and hold the Windows key on your keyboard and then press the "R" key to open up the "Run" box.

![](https://lh3.googleusercontent.com/lbvYIvW6ABJT8puA0gccHWYHJ1V-BstJ8dVxmxl5k3KM_CGX45M93zu-wuG4dqPA5gSGtNMSMW3TtXS03WT4PL94ei-Du6qnbBqD4ASsvXiMRrqhrJmywSHINTVnSubN_-tqBNZ-PVZ3OXDqmdND0w)

2. Type "cmd" into the text box and then click "OK".

![](https://lh5.googleusercontent.com/BG7mABh52Z0Ds5wYSNaDob5n3SzlRp3d-mGziagZTkz15jmPmJzOgBp3lGeoJ9wGI852UWt7-ON-ln1OQdhppXVgCmQCYm5yN7oRDuzOOBySNasF_hoTTXLS_Qx9Ji43mFy80VFWxHVyiS5IlQCPdQ)

3. In the black box that comes up type "ipconfig" and hit enter.

![](https://lh3.googleusercontent.com/utjloGeKUDgpLNwPt73KAaxx1QzmhPmUDAcbHQ4Y50E0AEjj1x52UhVVSKng1OeDTwbeuNNRRVwQZ6hFleHZlfRZ1PYjbdhhgQ6c-p_buTBjsl0EEPlY5JIM7QHiaIEzU0m5pRDtwGq4BC9LGxMVeg)

4. Look for the title "Ethernet adapter" and look for "IPV4 address", this is your local IP address. (The title may be "Wireless adapter" if you are on a wireless internet connection).

![](https://lh4.googleusercontent.com/xP-nPd-xvNSlenExGsrI40BapoQDHi-Bk7WhqAqtpmzkm02vcpnpMP44-839WDC-_wDlAqjyQYfnusEuCXQXBDAXFJnV9YcMvbcJdEivuqeqyI7IMt6R7Q0z4JeJS8s84J7szJUkAzTZOjCVa66JDQ)

## Find Operating Port

### Identify port used by SQL Server Database Engine using SQL Server Configuration Manager

1. Click Start -> Programs -> Microsoft SQL Server <Your Server Type: 2019, 2017, etc...> -> Configuration Tools -> SQL Server Configuration Manager

2. In SQL Server Configuration Manager, expand SQL Server Network Configuration and then select Protocols for <instance name> on the left panel. To identify the TCP/IP port used by the SQL Server Instance, right-click on TCP/IP and select Properties from the drop-down as shown below.

![](https://lh3.googleusercontent.com/gHmS2zfutvHR4AUmqe2L00yko6SWrqPlMao80LoaEHs5juvQjXeN_Ih0kjyiMEz5kkUm4cWHpLU9nF4ei8JXeMLY35hg2PPElNTbr8qO6mfC9wERgC6VmiJmA6cUJUIg5mltihkDQD6_LqNe-pmRKw)

*Note*: TCP/IP should be "Enabled". If it is not, "Enable" it and Restart the SQL Server.

3. In the TCP/IP Properties window click on the IP Addresses tab and you will see the Port used by the instance of SQL Server in either TCP Dynamic Ports for a dynamic port or TCP Port for a static port as highlighted in the snippet below.

### Identify port used by named instance of SQL Server Database Engine by reading SQL Server error logs

The SQL Server Error Log records information with respect to the port in which an instance of the SQL Server Database Engine is listening. You can execute the below T-SQL command which uses the XP_READERRORLOG extended stored procedure to read the SQL Server Error Log to find the port the SQL Server Database Engine is listening to.

```
 USE master GO xp_readerrorlog 0, 1, N'Server is listening on', 'any', NULL, NULL, N'asc'  GO
```

```
 --results  2018-11-16 23:19:41.730 Server Server is listening on [ 'any' <ipv6> 1433 ]. 2018-11-16 23:19:41.740 Server Server is listening on [ 'any' <ipv4> 1433].  2018-11-16 23:19:41.740 Server Server is listening on [ ::1 <ipv6> 1433].  2018-11-16 23:19:41.740 Server Server is listening on [ 127.0.0.1 <ipv4> 1433].
```

The parameters you can use with XP_READERRRORLOG are mentioned below for your reference:

1. Value of error log file you want to read: 0 = current, 1 = Archive #1, 2 = Archive #2, etc...
2. Log file type: 1 or NULL = error log, 2 = SQL Agent log
3. Search string 1: String one you want to search for
4. Search string 2: String two you want to search for to further refine the results
5. Search from the start time
6. Search to end time
7. Sort order for results: N'asc' = ascending, N'desc' = descending

## References

- [https://www.guru99.com/sql-server-create-user.html](https://www.guru99.com/sql-server-create-user.html)
- [https://docs.microsoft.com/en-us/sql/relational-databases/security/authentication-access/](https://docs.microsoft.com/en-us/sql/relational-databases/security/authentication-access/) create-a-database-user?view=sql-server-ver15
- [https://docs.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql?view=sql](https://docs.microsoft.com/en-us/sql/t-sql/statements/create-user-transact-sql?view=sql) server-ver15
- [https://docs.microsoft.com/en-us/sql/relational-databases/security/authentication-access/](https://docs.microsoft.com/en-us/sql/relational-databases/security/authentication-access/) database-level-roles?view=sql-server-ver15
- [https://docs.microsoft.com/en-us/sql/t-sql/statements/alter-role-transact-sql?view=sql-ser](https://docs.microsoft.com/en-us/sql/t-sql/statements/alter-role-transact-sql?view=sql-ser) ver-ver15
- [https://amberpos.zendesk.com/hc/en-us/articles/215978723-How-to-find-your-database-I](https://amberpos.zendesk.com/hc/en-us/articles/215978723-How-to-find-your-database-I) P-address-and-SQL-port
- [https://www.mssqltips.com/sqlservertip/2495/identify-sql-server-tcp-ip-port-being-used/](https://www.mssqltips.com/sqlservertip/2495/identify-sql-server-tcp-ip-port-being-used/)
- [https://www.sanssql.com/2011/02/different-ways-to-find-sql-server-port.html](https://www.sanssql.com/2011/02/different-ways-to-find-sql-server-port.html)
