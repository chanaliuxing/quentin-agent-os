# P9 External Audit Export Guide

## Overview
Quentin supports exporting signed audit bundles for third-party compliance reviews.

## Bundle Structure
- **manifest.json**: Metadata and integrity hashes.
- **events.jsonl**: Chronological log of governance decisions.
- **artifacts/**: Snapshots of code/configs at decision points.

## Verification
Use `scripts/audit_bundle_export.py` to package evidence and verify hashes.
