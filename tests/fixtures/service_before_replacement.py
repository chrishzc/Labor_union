"""Shared test facts for Scheduling service-before-replacement contracts."""

from domains.scheduling.service_before_replacement import (
    ActualServiceProof,
    ReplacementRootIdentity,
    ReplacementRootKind,
    ReplacementScenario,
    ServiceBeforeReplacementFacts,
    SuccessorRoundFact,
)


CASE = "CASE-RPRE-1"


def _root(kind: ReplacementRootKind, root_id: str, *, current: bool = True):
    return ReplacementRootIdentity(kind, root_id, CASE, current=current)


def _facts(
    scenario=ReplacementScenario.R02,
    *,
    service_dates=(),
    roots=None,
    proof=None,
    zero_candidate_proof=None,
):
    if roots is None:
        roots = tuple(
            _root(kind, f"{kind.value}:old")
            for kind in {
                ReplacementScenario.R01: (
                    ReplacementRootKind.CANDIDATE_BINDING,
                    ReplacementRootKind.WILLINGNESS,
                ),
                ReplacementScenario.R02: (
                    ReplacementRootKind.MATCHING_PLAN,
                    ReplacementRootKind.MATCHING_SEGMENT,
                    ReplacementRootKind.MATCHING_REPLY,
                    ReplacementRootKind.RECIPIENT_CONFIRMATION,
                ),
                ReplacementScenario.R03: (
                    ReplacementRootKind.WAITING_LOCK,
                    ReplacementRootKind.COMMITMENT,
                    ReplacementRootKind.SIGNBACK,
                    ReplacementRootKind.RECIPIENT_BINDING,
                ),
                ReplacementScenario.R04: (
                    ReplacementRootKind.EFFECTIVE_GENERATION,
                    ReplacementRootKind.ASSIGNMENT,
                    ReplacementRootKind.OFFICIAL_SCHEDULE,
                ),
                ReplacementScenario.R07: (),
            }[scenario]
        )
    service_proof = ActualServiceProof(
        CASE,
        tuple(service_dates),
        "official-service:event:old",
        13,
    )
    successor_round = None
    if scenario is ReplacementScenario.R07 and zero_candidate_proof is None:
        successor_round = SuccessorRoundFact(
            CASE,
            "successor-round:existing",
            "replacement-generation:existing",
            "replacement-event:existing",
            9,
            14,
            0,
            "zero_candidate_successor_disposition",
        )
    return ServiceBeforeReplacementFacts(
        CASE,
        scenario,
        tuple(service_dates),
        "generation:old",
        "event:old",
        8,
        13,
        roots,
        (_root(ReplacementRootKind.CANDIDATE_BINDING, "candidate:history", current=False),),
        proof,
        True,
        service_proof,
        8,
        "aggregate:old",
        CASE,
        "caregiver_requested_replacement",
        ("case-note:1",),
        successor_round,
        "round:1",
        "candidate:1",
        zero_candidate_proof,
    )
