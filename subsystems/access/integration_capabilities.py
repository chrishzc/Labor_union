"""Stable human capabilities for Contract and Knowledge administration."""

from enum import StrEnum


class IntegrationCapability(StrEnum):
    CONTRACT_EVIDENCE_READ = "contract.evidence.read"
    CONTRACT_EVIDENCE_MANAGE = "contract.evidence.manage"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_MANAGE = "knowledge.manage"
    KNOWLEDGE_PUBLISH = "knowledge.publish"
    KNOWLEDGE_REINDEX = "knowledge.reindex"


_ROLE_CAPABILITIES = {
    "line_viewer": {IntegrationCapability.KNOWLEDGE_READ},
    "line_agent": {IntegrationCapability.KNOWLEDGE_READ},
    "line_manager": set(IntegrationCapability),
    "system_admin": set(IntegrationCapability),
}


def integration_capabilities_for_role(role: str) -> tuple[str, ...]:
    capabilities = _ROLE_CAPABILITIES.get(role, set())
    return tuple(sorted(capability.value for capability in capabilities))


__all__ = ["IntegrationCapability", "integration_capabilities_for_role"]
