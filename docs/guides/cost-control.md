# Cost Control

AI agents are powerful but expensive. A runaway agent loop can burn through your API credits before you notice. Entourage gives you per-session tracking, team-level budgets, and kill switches.

## The problem

Without cost tracking:

- Agent enters a retry loop → 500k tokens burned in 10 minutes
- Multiple agents running overnight → surprise $50 bill
- No way to know which task cost what
- You find out from the Anthropic dashboard the next morning

With Entourage:

- Every session tracks tokens + dollars in real-time
- Budget caps stop agents before they exceed limits
- Per-task cost attribution
- Dashboard shows spend as it happens

## How tracking works

### Sessions

Every block of agent work is a **session**. When an agent starts working on a task, it opens a session:

```bash
curl -X POST http://localhost:8000/api/v1/agents/{agent_id}/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: oc_your_key_here" \
  -d '{
    "task_id": 594,
    "model": "claude-sonnet-4-20250514"
  }'
```

As the agent works, it reports token usage:

```bash
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/usage \
  -H "Content-Type: application/json" \
  -H "X-API-Key: oc_your_key_here" \
  -d '{
    "input_tokens": 2500,
    "output_tokens": 800,
    "cost_usd": 0.012
  }'
```

When done, the session closes:

```bash
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/end \
  -H "X-API-Key: oc_your_key_here"
```

All session endpoints require authentication (API key or JWT bearer token). See the [Getting Started](getting-started.md) guide for setting up authentication.

### Budget checks

Before expensive operations, agents call `check_budget`:

```bash
curl http://localhost:8000/api/v1/agents/{agent_id}/budget
```

Response:

```json
{
  "daily_limit_usd": 5.00,
  "daily_spent_usd": 3.42,
  "daily_remaining_usd": 1.58,
  "task_limit_usd": 2.00,
  "task_spent_usd": 0.85,
  "over_budget": false
}
```

If `over_budget` is true, the agent should stop and notify a human.

## Setting budgets

### Team-level daily cap

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/teams/{team_id} \
  -H "Content-Type: application/json" \
  -d '{"daily_cost_limit_usd": 10.00}'
```

This limits the **entire team** (all agents combined) to $10/day. Once hit, agents are told to stop.

### Per-task limits

When creating tasks, you can set cost caps:

```bash
curl -X POST http://localhost:8000/api/v1/teams/{team_id}/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Fix typo in README",
    "priority": "low",
    "task_type": "bugfix",
    "tags": ["budget:0.50"]
  }'
```

A typo fix shouldn't cost more than $0.50. If the agent burns more than that, something's wrong (probably a loop).

## Monitoring spend

### Team cost summary

```bash
curl http://localhost:8000/api/v1/teams/{team_id}/costs
```

Shows aggregated costs by agent, by time period:

```json
{
  "total_cost_usd": 4.23,
  "total_input_tokens": 125000,
  "total_output_tokens": 42000,
  "sessions": [
    {
      "agent_name": "eng-1",
      "task_title": "Fix login bug",
      "cost_usd": 1.85,
      "tokens": 55000,
      "duration_minutes": 12
    }
  ]
}
```

### Per-agent sessions

```bash
curl http://localhost:8000/api/v1/agents/{agent_id}/sessions
```

See every session an agent has had, with token counts and costs.

## Real-world budget guidelines

| Task type | Reasonable budget | Red flag |
|-----------|-------------------|----------|
| Typo / config fix | $0.10 - $0.50 | > $1 |
| Bug fix | $0.50 - $3.00 | > $5 |
| Small feature | $2.00 - $8.00 | > $15 |
| Large feature | $5.00 - $20.00 | > $30 |
| Daily team total | $10 - $50 | > $100 |

These vary by model. Sonnet is cheaper than Opus. Adjust based on your model choices.

## Common cost problems and fixes

### Agent stuck in a retry loop

**Symptom:** Token count spiking rapidly, same error in logs
**Fix:** End the session, fix the root cause, restart

```bash
curl -X POST http://localhost:8000/api/v1/sessions/{session_id}/end
```

### Agent generating too much output

**Symptom:** High output token counts relative to input
**Fix:** Tighten task descriptions. Vague tasks produce verbose responses.

Instead of: "Improve the codebase"
Write: "Add input validation to POST /users — reject emails without @ and passwords under 8 chars"

### Multiple agents duplicating work

**Symptom:** Two agents working on overlapping problems
**Fix:** Use DAG dependencies. If Task A and Task B touch the same files, make B depend on A.

### Overnight cost surprises

**Fix:** Set daily caps. If you're not monitoring overnight, set conservative limits:

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/teams/{team_id} \
  -H "Content-Type: application/json" \
  -d '{"daily_cost_limit_usd": 5.00}'
```

## Rate limiting

Entourage applies rate limiting to all API routes to prevent abuse and control resource usage.

### Default limits

| Route category | Default limit |
|---------------|---------------|
| General API routes | 100 requests per minute |
| Auth endpoints (`/auth/*`) | 10 requests per minute |

When a client exceeds the limit, the API returns `429 Too Many Requests` with a `Retry-After` header.

### Response headers

Every API response includes rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1709042460
```

### Configuration

The default rate limit is configurable via environment variable:

```bash
# In your .env file
OPENCLAW_RATE_LIMIT_RPM=100    # requests per minute for general routes
```

Auth endpoints are always limited to 10 rpm regardless of this setting, to protect against brute-force attacks.

### Rate limiting for agents

When running multiple agents, keep in mind that each agent's MCP tool calls go through the API. A team of 3 agents each making rapid tool calls can hit the 100 rpm limit. If you see `429` errors in agent sessions:

1. Increase the limit: `OPENCLAW_RATE_LIMIT_RPM=300`
2. Or stagger agent work using DAG dependencies so fewer agents run concurrently
