"""Pure state rules for direct knowledge publication."""

from enum import StrEnum


class KnowledgeState(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    RETIRED = "retired"


class KnowledgeTransitionError(ValueError):
    pass


def next_knowledge_state(current: KnowledgeState, action: str) -> KnowledgeState:
    transitions = {
        (KnowledgeState.DRAFT, "publish"): KnowledgeState.PUBLISHED,
        # Existing preserved rows may still be in the retired review state.
        (KnowledgeState.REVIEWED, "publish"): KnowledgeState.PUBLISHED,
        (KnowledgeState.PUBLISHED, "retire"): KnowledgeState.RETIRED,
    }
    next_state = transitions.get((current, action))
    if next_state is None:
        raise KnowledgeTransitionError("knowledge_state_conflict")
    return next_state
