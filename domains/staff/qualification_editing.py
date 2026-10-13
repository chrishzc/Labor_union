"""Staff-owned manually registered qualification and service facts."""
from dataclasses import dataclass
from collections.abc import Mapping

from shared_kernel.fingerprints import fingerprint_payload


class QualificationEditingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QualificationFacts:
    special_skills: tuple[str, ...]
    has_massage_cert: bool | None
    certifications: tuple[str, ...]
    care_babies: int | None
    transportation: tuple[str, ...]

    def payload(self):
        return {
            "special_skills": list(self.special_skills),
            "has_massage_cert": self.has_massage_cert,
            "certifications": list(self.certifications),
            "care_babies": self.care_babies,
            "transportation": list(self.transportation),
        }


def normalize_facts(values: Mapping[str, object]) -> QualificationFacts:
    fields = {"special_skills", "has_massage_cert", "certifications", "care_babies", "transportation"}
    if set(values) != fields:
        raise QualificationEditingError("staff_qualification_fields_invalid")

    def texts(key, maximum):
        items = values[key]
        if not isinstance(items, (list, tuple)) or len(items) > 100:
            raise QualificationEditingError("staff_qualification_list_invalid")
        normalized = []
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > maximum:
                raise QualificationEditingError("staff_qualification_text_invalid")
            normalized.append(item.strip())
        if len(set(normalized)) != len(normalized):
            raise QualificationEditingError("staff_qualification_duplicate_value")
        return tuple(sorted(normalized))

    massage = values["has_massage_cert"]
    care = values["care_babies"]
    if massage is not None and not isinstance(massage, bool):
        raise QualificationEditingError("staff_qualification_massage_invalid")
    if care is not None and (type(care) is not int or not 1 <= care <= 2147483647):
        raise QualificationEditingError("staff_qualification_care_babies_invalid")
    return QualificationFacts(texts("special_skills", 191), massage, texts("certifications", 191), care, texts("transportation", 50))


def snapshot_fingerprint(staff_id: int, facts: QualificationFacts):
    return fingerprint_payload({"staff_id": staff_id, "facts": facts.payload()})


def preview_fingerprint(staff_id: int, before: QualificationFacts, after: QualificationFacts):
    return fingerprint_payload({"staff_id": staff_id, "before": before.payload(), "after": after.payload()})
