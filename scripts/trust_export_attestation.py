import json
from quentin.trust.attestation_builder import AttestationBuilder

def main():
    builder = AttestationBuilder()
    
    # Mock telemetry
    telemetry = {"policy_compliance_rate": 0.99, "safety_incidents": 0}
    
    attestation = builder.build(telemetry)
    print(json.dumps(attestation.__dict__, indent=2))

if __name__ == "__main__":
    main()
