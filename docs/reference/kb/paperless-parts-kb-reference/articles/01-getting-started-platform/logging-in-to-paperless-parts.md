---
title: "Logging into Paperless Parts"
slug: logging-in-to-paperless-parts
source: https://help.paperlessparts.com/s/article/logging-in-to-paperless-parts
topic: "Getting Started & Platform"
captured: 2026-06-19
---

# Logging into Paperless Parts

> Source: https://help.paperlessparts.com/s/article/logging-in-to-paperless-parts  
> Topic: Getting Started & Platform

Paperless Parts supports Single Sign-On (SSO) to streamline the authentication process and enhance security. For users in federal agencies, SSO can be configured using Security Assertion Markup Language (SAML), allowing integration with existing SAML profiles. Federal users can utilize Personal Identity Verification (PIV) or Common Access Card (CAC) credentials to authenticate via SAML. Contact support for assistance in configuring SSO with SAML and/or PIV/CAC credentials.

Paperless Parts supports the following authenticators:

- Third-party authenticators via SAML
- Paperless Parts username/password combined with TOTP second factor

For customers requiring CMMC, it is the customer's responsibility to ensure third-party authenticators used for SSO are compliant with relevant controls.

#### On this page:

- [How do I create an account in Paperless Parts?](#h.z0263uko4vyu)
- [How do I log in to Paperless Parts?](#h.rl5vwtm6pz5w)
- [Single sign-on (SSO)](#h.svyyui259gay)
  - [How do I set up single sign-on?](#h.bas78gjq9q9w)
  - [How do I log in with single sign-on?](#h.e9v74qxpxukt)
- [Having trouble logging in?](#h.e19hw9tdi2ia)
  - [You're not logging in with an email address](#h.zcujwagulhq3)
  - [You're not using the email address associated with your account](#h.pw2k183ufrru)
  - [You're trying to log in via SSO without SSO configured (and vice-versa)](#h.adi17gj23lyz)
  - [You never confirmed your account](#h.odbxaqlp3k32)

---

# How do I create an account in Paperless Parts?

Creating an account in Paperless Parts requires [an invitation](https://help.paperlessparts.com/s/article/team-page-and-user-permissions#add), either from an existing user in your organization or a member of our team.

The invite will come as an email with the subject line "Welcome to Paperless Parts!".

![](https://lh4.googleusercontent.com/-BJeag1wLlXCDTtuZAgdQTR_gYvlqf3iS6HsQq52JinM7jbCbhSgf1JCW8XlQ0j879aoGdJ3-GSmeYYLUIsRijwBwGtnQFTLHX5UlOaBYg3vhbLtbehLNPzbR3OUbuh5BOr4dQpCQMzQKVaa1UhBfDY)

Click **Create your user account** to get started.

![](https://lh3.googleusercontent.com/H_SdoPZjhs1jzLPeYOZkZPFFn7UW4-thEsBFiO-GGmXz_BE9iQb3dk8c8Idxne6Rbd60fYnuxzchVrQ-cVDGciuLKJZU7uFmfDQChdqcyI29E4fMrOvDRWlr6GigmR6qD-eZPjQaJhpQ2uO2RJBah7o)

Once you've created a unique password and accepted the Terms of Use, select **Create account** to confirm.

After setting up your account, you'll receive an email from [support@paperlessparts.com](mailto:support@paperlessparts.com) prompting you to verify your email address. Click the link in the email to finish setting up your account.

# How do I log in to Paperless Parts?

To log into Paperless Parts:

1. Navigate to app.paperlessparts.com.
2. Enter your email and unique password.

![](https://lh5.googleusercontent.com/rZkwjY6cCcWn-5lFY1zj_0XJ_p0uC64G17F2JtNWI77ijXNl16-DNvYg_u7S-jjU8_fMPaZIf3Emn3im-B0JETX9yR-P4sQTxiSa0LpBYwb8gUFeci09W9EV2SlXQ_JayH_jW9BP_TPIvT-MFlh1xwk)

Some organizations require two-factor authentication (2FA) in order to log in. If this is true for your group, you'll be prompted to enter a 2FA code after correctly entering your login information. Learn more about 2FA and Paperless Parts [here](https://help.paperlessparts.com/s/article/two-factor-authentication-2fa).

*Tip*: Because Paperless Parts is browser-based, each page has its own unique URL. Once you're logged in, bookmark app.paperlessparts.com (or whichever page in the app you reference most regularly) in your browser to quickly navigate to your account.

# Single sign-on (SSO)

If your shop uses an identity provider (IdP), such as Microsoft Azure Active Directory, you can implement single sign-on (SSO) for your organization.

Once SSO is enabled for your organization, team members will only be able to log in via your IDP. That means that a user must exist in both Paperless Parts and your IDP to access their account within your organization.

![](https://s3.amazonaws.com/helpscout.net/docs/assets/5be4842c04286304a71c0d57/images/6422f2ccb282ac0ba214c02b/file-Kg058qaRyM.png)

*Note*: Vendors and outside parties that you communicate with via external chat are not members of your organization, so implementing SSO will not affect their ability to log in.

## How do I set up single sign-on?

SSO needs to be configured for your organization by a Paperless Parts team member. As part of the process, your shop will need to export the IDP metadata file from your IDP and [upload it into your](https://www.google.com/url?q=https://help.paperlessparts.com/s/article/getting-started%23upload&sa=D&source=editors&ust=1676499176711049&usg=AOvVaw03coe5ydIEDHiHpmEKtuT5)[Part Library.](https://www.google.com/url?q=https://help.paperlessparts.com/s/article/getting-started%23upload&sa=D&source=editors&ust=1676499176711432&usg=AOvVaw1RfoPschmOPJKrHb2v24BO)

SSO is available as part of the Aerospace and Defense package. Reach out to your primary contact at Paperless Parts or [our Support team](mailto:support@paperlessparts.com) to get started.

## How do I log in with single sign-on?

1. Navigate to app.paperlessparts.com.
2. Select **Single sign-on**.
3. Enter your email and click **Single sign-on**. If your account has an IDP configured, you will be forwarded to your IDP login page.
4. Log in through your IDP.

# Having trouble logging in?

Below, we've listed a few common reasons you may run into trouble logging in and their potential solutions.

If these fixes don't do the trick, reach out to your account administrator for help. Each organization has an assigned admin who can add and remove team members. [Our Support team](mailto:support@paperlessparts.com) is always available to assist, but for security reasons, we encourage you to try to resolve login issues internally before reaching out.

## You're not logging in with an email address

Some other manufacturing software (like ERP systems) require you to sign in with your last name rather than an email. Make sure that you're using your email address to log in rather than a username.

## You're not using the email address associated with your account

The email address that you use to log in must match the email address associated with your account, which is listed on the Team page.

![](https://lh4.googleusercontent.com/hym21gy2wbIJPbmYYRtkmBoR8uaboeII6GWQ_rLZ8AEKBGoXLtwLMxJmh1MNZKyAUmfzMvW3msSzkk3320v4UM1y2dKfBp83564zvp8gPOTn5IM0MjoliuWJ6qxz9rvrAdXTAnH-LM2hw5NyH1tKLRc)

## You're trying to log in via SSO without SSO configured (and vice-versa)

If your organization [has SSO configured](#h.svyyui259gay), you'll need to select **Single sign-on** at the login screen and log in via your IDP.

Similarly, if your shop uses an IDP and you are unable to login via SSO, you may not have SSO configured in your Paperless Parts organization. Click [here](#h.bas78gjq9q9w) for details on enabling SSO for your team.

## You never confirmed your account

Once you create an account in Paperless Parts, you'll receive an email from [support@paperlessparts.com](mailto:support@paperlessparts.com) prompting you to verify your email address. Click the link in the email to finish setting up your account.
