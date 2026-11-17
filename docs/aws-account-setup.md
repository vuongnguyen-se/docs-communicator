# AWS Account Setup (Phase 0: P0-01 to P0-04)

You do this once. Nothing here costs money. Never paste passwords, MFA codes or access keys into chat or commit them to git.

AWS console wording changes from time to time. If a button name differs slightly, look for the closest match.

---

## Step 1: Lock down the root user (P0-01a)

The **root user** is the email and password you signed up with. It can do anything, including closing the account, so you use it only for account-level tasks.

1. Sign in at https://console.aws.amazon.com as **Root user**.
2. Click your account name (top right) → **Security credentials**.
3. **Multi-factor authentication (MFA)** → **Assign MFA device**. Use a passkey, security key or authenticator app (Google Authenticator, Microsoft Authenticator, 1Password, …).
4. On the same page, under **Access keys**, make sure there are **none**. If any exist, delete them. Root must never have access keys.
5. Account name menu → **Account** → **IAM user and role access to Billing information** → **Edit** → tick **Activate**. This lets your admin user (step 2) see bills.

✅ Done when: root shows an assigned MFA device and 0 access keys.

## Step 2: Create your day-to-day admin identity (P0-01b)

We use **IAM Identity Center** (single sign-on). The CLI then gets **short-lived credentials** through a browser login, so there are no permanent access keys on your laptop that could leak.

1. Still as root, switch the Region (top right) to **Asia Pacific (Singapore) ap-southeast-1**. Identity Center lives in one Region, so choose it before enabling it.
2. Search for **IAM Identity Center** → **Enable** (choose an *organization instance* if asked; this enables AWS Organizations automatically and is free).
3. **Users** → **Add user**: username, e.g. `vuong-admin`, with your email → **Next** → skip groups → **Add user**.
4. **Permission sets** → **Create permission set** → **Predefined** → `AdministratorAccess` → set the session duration to e.g. **4 hours** → create.
   - *Why admin:* CDK needs to create IAM roles, Lambdas, Cognito and more. The app's own Lambdas still get least-privilege roles. Admin is only for you, the deployer.
5. **AWS accounts** → tick your account → **Assign users or groups** → select `vuong-admin` → select `AdministratorAccess` → **Submit**.
6. Open the invitation email → **Accept** → set a password → **register an MFA device** (required).
7. Back on the Identity Center **Dashboard**, copy the **AWS access portal URL** (looks like `https://d-xxxxxxxxxx.awsapps.com/start`). You need it in step 3.
8. Sign out of root. From now on, use the access portal URL.

✅ Done when: you can open the access portal, see your account with `AdministratorAccess` and open the console from there.

## Step 3: Connect the AWS CLI (P0-02)

Run this in PowerShell or cmd (not inside Claude, because it is interactive):

```powershell
aws configure sso
```

Answer the prompts:

| Prompt | Answer |
|---|---|
| SSO session name | `clouddocs` |
| SSO start URL | your access portal URL from step 2.7 |
| SSO region | `ap-southeast-1` |
| SSO registration scopes | press Enter (default) |
| *(browser opens → approve the request)* | |
| Account / role | pick your account and `AdministratorAccess` |
| Default client Region | `ap-southeast-1` |
| CLI default output format | `json` |
| Profile name | `clouddocs-dev` |

Test it:

```powershell
aws sts get-caller-identity --profile clouddocs-dev
```

It should print your account ID and an ARN containing `AWSReservedSSO_AdministratorAccess`. Don't paste the account ID anywhere public, including the GitHub repository.

**Daily use:** credentials expire after the session duration. When a command says the token expired, run:

```powershell
aws sso login --profile clouddocs-dev
```

Optional, so you don't need `--profile` every time in this PowerShell window: `$env:AWS_PROFILE = "clouddocs-dev"`.

✅ Done when: `get-caller-identity` works.

## Step 4: Budget alert (P0-03)

A budget **does not stop spending**. It emails you, so you notice forgotten resources quickly.

1. Console → **Billing and Cost Management** → **Budgets** → **Create budget**.
2. **Use a template** → **Monthly cost budget**.
3. Name `clouddocs-monthly`, amount e.g. **10 USD**, and your email as recipient.
4. Create it. Then **edit** it and add alert thresholds so you have: **50% actual**, **80% actual**, **100% actual** and **100% forecasted**.
5. Optional but recommended, and free: **Cost Anomaly Detection** → create a monitor for **AWS services** with an email alert.

✅ Done when: the budget is listed and you received or confirmed the alert email.

## Step 5: Cost allocation tag (P0-04)

All project resources will be tagged `Project=CloudDocsAI`. To see the project's cost separately in Cost Explorer:

1. **Billing and Cost Management** → **Cost allocation tags**.
2. The `Project` tag only appears **after** the first tagged resource exists (Phase 0 spike or Phase 1 deploy). Come back then, select it and click **Activate**.

✅ Done when: `Project` shows as **Active**. It is fine to finish this step later.

---

## After this: what Claude does next (P0-05, P0-06)

Once `aws sts get-caller-identity --profile clouddocs-dev` works, Claude runs **read-only** checks. They create nothing and cost nothing:

```powershell
aws bedrock list-foundation-models --region ap-southeast-1 --profile clouddocs-dev
aws bedrock list-inference-profiles --region ap-southeast-1 --profile clouddocs-dev
```

Some providers' models (for example Anthropic's) need a one-time **use-case form** in the Bedrock console before first use. If the check shows one is needed, you'll fill it in yourself.
