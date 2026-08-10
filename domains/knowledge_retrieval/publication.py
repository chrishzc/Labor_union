"""Pure state and separation rules for reviewed knowledge publication."""

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
        (KnowledgeState.DRAFT, "review"): KnowledgeState.REVIEWED,
        (KnowledgeState.REVIEWED, "publish"): KnowledgeState.PUBLISHED,
        (KnowledgeState.PUBLISHED, "retire"): KnowledgeState.RETIRED,
    }
    next_state = transitions.get((current, action))
    if next_state is None:
        raise KnowledgeTransitionError("knowledge_state_conflict")
    return next_state


def require_separate_publisher(creator_id: int, publisher_id: int) -> None:
    if creator_id == publisher_id:
        raise KnowledgeTransitionError("knowledge_publisher_separation_required")


def require_separate_reviewer(creator_id: int, reviewer_id: int) -> None:
    if creator_id == reviewer_id:
        raise KnowledgeTransitionError("knowledge_reviewer_separation_required")
