domain: contract-signing
architecture: ../../../domains/contract-signing/index.md
test_root: tests/domains/contract-signing/
integration_root: tests/domains/contract-signing/subsystems/contract-signing/integration/
fixtures_root: tests/fixtures/
subsystems:
  contract-signing:
    index: subsystems/contract-signing/index.md

# Routing notes
Contract Signing domain rules, Q/P/A workflows, API adapters, renderer/PDF adapters, signing repositories and owner-specific historical-baseline adapters route to the canonical Contract Signing subsystem root when the direct SUT is owned by Contract Signing. Cross-owner collaborators may be faked without changing ownership.
