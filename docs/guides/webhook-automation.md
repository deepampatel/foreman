# Webhook Automation

Instead of manually creating tasks when GitHub issues come in, let Entourage listen for webhooks and auto-create work for your agents. This guide shows how to wire up GitHub → Entourage.

## How it works

```
GitHub issue created
        ↓
POST /webhooks/{id}/receive
        ↓
Verify HMAC-SHA256 signature
        ↓
Log delivery in webhook_deliveries
        ↓
Process event → create/update task
        ↓
Emit event via Redis pub/sub
        ↓
Dashboard updates in real-time
```

Every webhook delivery is logged. You can see what came in, whether it was processed, and what action was taken.

## Step 1: Register a webhook

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "{org_id}",
    "provider": "github",
    "events": ["issues.opened", "issues.closed", "pull_request.opened", "pull_request.merged"],
    "config": {
      "team_id": "{team_id}",
      "auto_assign": true
    }
  }'
```

Response:

```json
{
  "id": "webhook-uuid",
  "secret": "whsec_abc123...",
  "events": ["issues.opened", "issues.closed", "pull_request.opened", "pull_request.merged"],
  "active": true
}
```

Save the `secret` — you'll need it when configuring GitHub.

## Step 2: Configure GitHub

In your GitHub repo: **Settings → Webhooks → Add webhook**

| Field | Value |
|-------|-------|
| Payload URL | `https://your-server.com/api/v1/webhooks/{webhook_id}/receive` |
| Content type | `application/json` |
| Secret | The `secret` from Step 1 |
| Events | Select "Issues" and "Pull requests" |

For local development, use a tunnel like [ngrok](https://ngrok.com):

```bash
ngrok http 8000
# Use the ngrok URL as your Payload URL
```

## Step 3: Verify it works

Create a GitHub issue. Entourage receives the webhook, verifies the HMAC signature, and processes it.

Check deliveries:

```bash
curl http://localhost:8000/api/v1/webhooks/{webhook_id}/deliveries
```

```json
[
  {
    "id": "delivery-uuid",
    "event_type": "issues.opened",
    "status": "processed",
    "payload_summary": {"action": "opened", "issue": {"title": "Login broken on Safari"}},
    "created_at": "2026-02-27T..."
  }
]
```

## What happens for each event

### `issues.opened` → Task created

When someone opens a GitHub issue, Entourage can auto-create a task:

```
GitHub Issue: "Login broken on Safari"
  ↓
Entourage Task:
  title: "Login broken on Safari"
  priority: medium
  task_type: bugfix
  status: todo
  tags: ["github", "issue:42"]
```

If `auto_assign` is enabled in webhook config, the task gets assigned to the team's first available engineer.

### `issues.closed` → Task status updated

When the GitHub issue is closed, the corresponding task is updated to reflect it.

### `pull_request.opened` → Review triggered

A new PR can trigger Entourage's review pipeline — an agent reviews the code using the same structured review system (file-anchored comments, approve/reject/request-changes).

### `pull_request.merged` → Task completed

When a PR merges, the associated task moves to `done`.

## Security: HMAC-SHA256 verification

Every incoming webhook is verified using HMAC-SHA256:

```
Expected signature = HMAC-SHA256(webhook_secret, raw_request_body)
Actual signature   = X-Hub-Signature-256 header from GitHub
```

If they don't match, the request is rejected with 401. This prevents:
- Spoofed webhook calls
- Replay attacks
- Tampered payloads

## Filtering events

You don't have to process everything. The `events` array controls what gets processed:

```bash
# Only listen for new issues
curl -X PATCH http://localhost:8000/api/v1/webhooks/{webhook_id} \
  -H "Content-Type: application/json" \
  -d '{"events": ["issues.opened"]}'
```

Events not in the list are still logged (for audit) but not processed.

## Monitoring webhooks

### Check webhook status

```bash
curl http://localhost:8000/api/v1/webhooks/{webhook_id}
```

### List all deliveries

```bash
curl http://localhost:8000/api/v1/webhooks/{webhook_id}/deliveries
```

Shows every delivery with status (`received`, `processed`, `failed`), timestamps, and payload summaries.

### Regenerate secret

If your webhook secret is compromised:

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/{webhook_id}/regenerate-secret
```

Update the new secret in GitHub settings.

## Example: Full GitHub → Entourage pipeline

```
1. Developer opens GitHub issue: "Add dark mode support"
2. GitHub sends webhook → Entourage
3. Entourage creates Task: "Add dark mode support" (status: todo)
4. Manager agent decomposes into sub-tasks:
   - "Add theme context provider" → eng-frontend
   - "Create dark color palette" → eng-frontend
   - "Add toggle to settings page" → eng-frontend (depends on above)
5. Engineers work through MCP tools
6. Each sub-task goes through code review
7. After all sub-tasks merge → parent task closes
8. Entourage can update the GitHub issue: "Resolved in tasks #601-#603"
```

The entire flow from issue to deployed fix is tracked, reviewed, and auditable.
