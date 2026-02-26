"""Real-time infrastructure — Redis pub/sub + WebSocket.

Learn: Events flow through two channels:
1. Services → Redis PUBLISH (backend-side broadcast)
2. Redis SUBSCRIBE → WebSocket → Frontend (real-time delivery)

This decouples event producers (services) from consumers (WebSocket clients).
"""
