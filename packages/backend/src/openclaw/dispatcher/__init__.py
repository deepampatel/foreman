"""Multi-agent dispatcher — PG LISTEN/NOTIFY for instant message dispatch.

Learn: The dispatcher is a separate process that:
1. Listens for new_message notifications via PostgreSQL LISTEN/NOTIFY
2. On notification → dispatches agent turns with concurrency control
3. Publishes real-time events to Redis for the WebSocket layer

This replaces Delegate's polling-based dispatch (1s lag) with
instant notification (<100ms latency).
"""
