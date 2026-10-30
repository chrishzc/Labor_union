module: table-image-delivery
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/table-image-delivery.md
test_root: tests/domains/external-integration/subsystems/line/modules/table-image-delivery/

# Owned verification
Picture tokens are opaque, purpose-bound and expire; invalid tokens never open DB. Reads use immutable delivery data and never commit. Provider payloads omit internal data. Both workflows preserve actions, initial privacy and independent editable action copy. PNG renderer wraps complete text and does not write files. Public/private routes preserve machine and signed-picture gates.
