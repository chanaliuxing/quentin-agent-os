# P6 Signing and Publish Guide

## Supply Chain Security
All external plugins must be signed by a trusted publisher.

## Signing Process
1. Generate a SHA256 hash of your `manifest.json`.
2. Sign the hash using your secret/private key (HMAC-SHA256 for demo).
3. Include the signature in your `PluginInfo`.

## Verification
Quentin verifies the signature against the `MarketIndex` and `PluginSignatureVerifier` before installation. Unsigned or mismatched plugins will be rejected.
