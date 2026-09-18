# Tests: M2 feedback owner

architecture: ../../../../../../domains/external-integration/subsystems/line/modules/feedback.md
test_root: tests/domains/external-integration/subsystems/line/modules/feedback/
integration_root: tests/domains/external-integration/subsystems/line/infrastructure/test_line_feedback_knowledge_owner_flow.py
integration_root: tests/domains/external-integration/subsystems/line/infrastructure/test_line_feedback_knowledge_source_validation.py
integration_root: tests/domains/external-integration/subsystems/line/infrastructure/test_line_feedback_transaction_failures.py
integration_root: tests/domains/external-integration/subsystems/line/infrastructure/test_line_service_help_feedback_page.py

The canonical owner-local tests protect immutable terminal feedback, exact replay, conflict, Customer Service linkage and recomputed aggregate semantics.
