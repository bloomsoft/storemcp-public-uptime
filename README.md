# StoreMCP public uptime

Public, credential-free availability checks for StoreMCPAccess. This repository contains no private app source, Shopify access tokens, customer data, database files or operational credentials.

The standard Ubuntu runner checks the public web application, exact OAuth discovery identity, a minimal monitoring heartbeat and MCP authentication boundary. The heartbeat exposes only a schema version, health flag and timestamp; unhealthy or older-than-five-minute responses fail the probe. It never executes a Shopify tool. Redirects, TLS errors, placeholder pages, unexpected issuers and missing authentication challenges fail the check. Remote response bodies and exceptions are not logged.

Run locally with Python 3:

```sh
python3 -m unittest -v
python3 probe.py
```

The manual workflow's **simulate_failure** input tests a failure notification without stopping or changing the application.

Scheduled checks are configured every 15 minutes but remain gated until repository variable **MONITOR_ENABLED=true**. Manual runs are allowed while gated. Email delivery must be verified before enabling that variable. GitHub's Actions email notification preferences control delivery; no SMTP or Gmail credential is stored here.

The job is skipped before runner allocation if this repository becomes private. It uses standard ubuntu-24.04 runners, no caches or artifacts, and a two-minute timeout. Standard public-repository runners are [free](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

GitHub schedules are best-effort, can be delayed or dropped, and can be disabled after repository inactivity. This is not a guaranteed 15-minute SLA. The heartbeat reports the private collector's aggregate health/freshness decision without exposing its data. The monitor does not independently inspect database records, verify every backup's decryptability or execute authenticated tools. See [schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) and [workflow notification settings](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications).
