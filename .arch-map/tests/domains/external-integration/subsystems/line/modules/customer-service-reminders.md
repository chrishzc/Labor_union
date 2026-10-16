# Tests: Customer Service reminders

architecture: ../../../../../../domains/external-integration/subsystems/line/modules/customer-service-reminders.md

test_root: tests/domains/external-integration/subsystems/line/modules/customer-service-reminders/
UI integration coverage follows the parent LINE test ownership; the reminder cases and fixture remain in its canonical integration directory.

Owner SQL is exercised against isolated in-memory facts; reader transport, true pagination, multi-source de-duplication and zero-write behavior remain observable. UI tests protect the reminder-only contract and retirement of the desktop reply/resolve drawer, without retiring the legacy API or mobile workflows.
