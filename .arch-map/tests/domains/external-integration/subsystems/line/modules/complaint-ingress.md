subsystem: line
parent_domain: external-integration
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/complaint-ingress.md
test_root: tests/domains/external-integration/subsystems/line/modules/complaint-ingress/
fixtures_root: tests/fixtures/

# Routing notes

The contract test covers the canonical complaint source normalizer, masked
Customer Service escalation creation in the caller UoW, HIGH urgency/hold
intent, safe ticket payload, and durable empathy delivery. It does not invoke a
LINE provider or create Payroll/assignment facts.
