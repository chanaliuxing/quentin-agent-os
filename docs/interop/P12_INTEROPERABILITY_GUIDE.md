# P12 Interoperability Guide

## Translation Layer
The `InteropBridge` translates Quentin internal events to industry standards (e.g., OpenTelemetry).

## Safety First
All external data must pass through the `InteropSafetyGate` to redact secrets and PII before reaching the Quentin core.

## Supported Formats
- **Internal**: Native JSON with OQS schemas.
- **External**: OpenTelemetry (logs/traces), JSON-RPC (tools).
