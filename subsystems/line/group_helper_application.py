"""
File: group_helper_application.py
Description: 處理案件群組月嫂小幫手選單、開工日、合意延期與排程（零推播）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
import re
from typing import Any, Callable, Sequence
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from pymysql.constants.ER import DUP_ENTRY
from pymysql.err import IntegrityError

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineGroupId, LineSourceType, LineUserId
from domains.line.order_group import LineOrderGroupBindingSnapshot, LineOrderGroupBindingStatus
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.scheduling.leave_result import LeaveDateChange, LeaveResultSubmission
from domains.scheduling.service_start import (
    ServiceStartConflict,
    ServiceStartDecision,
    ServiceStartSubmission,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey, IdempotencyReceipt
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.message_copy_catalog import configured_payload
from subsystems.line.navigation_catalog import load_persisted_aliases
from subsystems.line.service_start_messages import (
    HELPER_TEXT_DEFAULTS,
    GROUP_ASSISTANCE_DIRECTIONS,
    SATISFACTION_SURVEY_ACTION,
    case_information_card,
    confirm_start_date_card,
    group_guidelines_card,
    group_helper_menu_card,
    mutual_postponement_card,
    mutual_postponement_entry_card,
    render_group_helper_menu_state,
    service_date_record,
    service_schedule_calendar_card,
)

_ACTIVE_BINDING_STATUSES = frozenset({
    LineOrderGroupBindingStatus.BOUND,
    LineOrderGroupBindingStatus.INVITING,
    LineOrderGroupBindingStatus.ACTIVE,
    LineOrderGroupBindingStatus.ATTENTION,
})
_DEFAULT_MENU_ALIASES = ("小幫手", "工會", "月嫂選單", "服務選單")
_DEFAULT_POSTPONE_PREFIXES = ("雙方合意延期",)
_POSTPONEMENT_RANGE_RE = re.compile(
    r"[：:]\s*(\d{4}-\d{2}-\d{2}(?:[、,]\s*\d{4}-\d{2}-\d{2})*)\s*(?:順延至|延至|->|→)\s*(\d{4}-\d{2}-\d{2}(?:[、,]\s*\d{4}-\d{2}-\d{2})*)\s*$"
)
_POSTPONEMENT_SEND_PREFIX = "雙方合意延期 提案 "
_POSTPONEMENT_NOTICE_PREFIX = "雙方合意延期申請已送出，請確認是否同意日期調整。\n提案編號："
_POSTPONEMENT_SEND_RE = re.compile(
    re.escape(_POSTPONEMENT_SEND_PREFIX) + r"(?P<proposal_ref>[0-9a-f]{32})"
    + "|" + re.escape(_POSTPONEMENT_NOTICE_PREFIX)
    + r"(?P<notice_case>[^\r\n]{1,50})-(?P<notice_revision>[1-9][0-9]{0,18})"
)


def _match_postponement_text(text: str, prefixes: tuple[str, ...]) -> re.Match[str] | None:
    for prefix in sorted(prefixes, key=len, reverse=True):
        if text.startswith(prefix):
            return _POSTPONEMENT_RANGE_RE.fullmatch(text[len(prefix):].lstrip())
    return None
_FAMILY_START_PROPOSAL = "group_helper_start_proposal"
_FAMILY_POSTPONE_PROPOSAL = "group_helper_postpone_proposal"
POSTPONEMENT_DRAFT_FAMILY = "group_helper_postpone_draft"
POSTPONEMENT_NOTICE_FAMILY = "group_helper_postpone_notice"
_FAMILY_POSTPONE_CARD = "group_helper_postpone_card"
_TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def _extract_group_id(source: Any) -> str | None:
    source_id = getattr(source, "source_id", None)
    if isinstance(source_id, str) and source_id.strip():
        return source_id.strip()
    group_obj = getattr(source, "group_id", None)
    group_val = getattr(group_obj, "value", None)
    return group_val.strip() if isinstance(group_val, str) and group_val.strip() else None


def _message_text(inbox: Any) -> str | None:
    payload = json.loads(inbox.event.payload_json)
    message = payload.get("message")
    if not isinstance(message, dict) or message.get("type") != "text":
        return None
    text = message.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _postback_info(inbox: Any) -> tuple[str, dict[str, Any]]:
    payload = json.loads(inbox.event.payload_json)
    postback = payload.get("postback")
    if not isinstance(postback, dict):
        return "", {}
    data = postback.get("data")
    params = postback.get("params")
    return (
        data.strip() if isinstance(data, str) else "",
        params if isinstance(params, dict) else {},
    )


def _iso_date_or_none(raw: object) -> date | None:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _canonical_mode(service_type: str | None) -> str:
    raw = (service_type or "").strip()
    if "休假" in raw or "六日" in raw or "二日" in raw or "2日" in raw:
        return "休六日"
    return "休周日" if not raw else raw


def _compute_expected_end_date(start_day: date, service_days: int, service_type: str | None) -> date:
    from infrastructure.mysql.mysql_adapter import calculate_attendance_schedule

    mode = _canonical_mode(service_type)
    result = calculate_attendance_schedule(start_day, int(service_days or 20), mode)
    end_val = _iso_date_or_none(result.get("actual_end_date"))
    return end_val or (start_day + timedelta(days=max(0, int(service_days or 20) - 1)))


def _default_staff_schedule_url(case_no: str, mode: str) -> str:
    query = urlencode({"case_no": case_no, "mode": mode, "group_reply": "1"})
    liff_id = os.getenv("LINE_STAFF_SCHEDULE_LIFF_ID", "").strip()
    if liff_id and liff_id != "your_liff_id_here":
        return f"https://liff.line.me/{liff_id}/?{query}"
    liff_id = os.getenv("LINE_LIFF_ID", "").strip()
    if liff_id and liff_id != "your_liff_id_here":
        return f"https://liff.line.me/{liff_id}/line-staff-schedule?{query}"
    base_url = (
        os.getenv("LINE_PUBLIC_BASE_URL", "").strip()
        or os.getenv("BASE_URL", "").strip()
    ).rstrip("/")
    placeholders = {"https://your-public-domain.example", "https://your-domain.example.com"}
    if base_url and base_url not in placeholders:
        return f"{base_url}/line-staff-schedule?{query}"
    return f"http://127.0.0.1:8000/line-staff-schedule?{query}"


def load_group_helper_proposal(
    unit_of_work: Any,
    family: str,
    case_no: str,
    event_id: str,
    *,
    current_read: bool = False,
) -> dict[str, Any] | None:
    """Read the immutable receipt for a specific proposal, including older proposals."""
    conn = getattr(unit_of_work, "_connection", None)
    if conn is None:
        return getattr(unit_of_work, "_helper_proposals", {}).get((family, case_no, event_id))
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT result_snapshot FROM line_command_receipts "
            "WHERE idempotency_key=%s AND command_family=%s AND correlation_id=%s"
            + (" FOR SHARE" if current_read else ""),
            (f"{family}:{case_no}:{event_id}"[:191], family, f"case:{case_no}"[:191]),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    raw = row["result_snapshot"]
    return json.loads(raw) if isinstance(raw, str) else raw


def save_group_helper_proposal(
    unit_of_work: Any,
    family: str,
    case_no: str,
    event_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Append an immutable proposal snapshot for in-group start-date or postponement flows."""
    conn = getattr(unit_of_work, "_connection", None)
    fp = fingerprint_payload(payload).value
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    key_str = f"{family}:{case_no}:{event_id}"[:191]
    corr_str = f"case:{case_no}"[:191]
    ref_str = (
        "cleared"
        if payload.get("cleared")
        else str(payload.get("start_date") or payload.get("leave_end_date") or "proposed")[:191]
    )
    if conn is not None:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO line_command_receipts "
                    "(idempotency_key,command_family,payload_fingerprint,result_reference,result_snapshot,correlation_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (key_str, family, fp, ref_str, serialized, corr_str),
                )
        except IntegrityError as error:
            if error.args[0] != DUP_ENTRY:
                raise
            # A concurrent insert may have committed after our transaction's read snapshot.
            saved = load_group_helper_proposal(unit_of_work, family, case_no, event_id, current_read=True)
            if saved is None:
                raise
            return saved
        return payload
    store = getattr(unit_of_work, "_helper_proposals", None)
    if isinstance(store, dict):
        receipt_key = (family, case_no, event_id)
        if receipt_key in store:
            return store[receipt_key]
        store[receipt_key] = payload
        store[(family, case_no)] = payload
    receipts = getattr(unit_of_work, "receipts", None)
    if receipts is not None:
        from shared_kernel.fingerprints import PreviewFingerprint

        key = IdempotencyKey(key_str)
        if receipts.get(key) is None:
            receipts.append(IdempotencyReceipt(key, PreviewFingerprint(fp), ref_str))
    return payload


def load_latest_group_helper_proposal(
    unit_of_work: Any,
    family: str,
    case_no: str,
    *,
    current_read: bool = False,
    include_cleared: bool = False,
) -> dict[str, Any] | None:
    conn = getattr(unit_of_work, "_connection", None)
    if conn is not None:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT result_snapshot FROM line_command_receipts "
                "WHERE command_family=%s AND correlation_id=%s ORDER BY id DESC LIMIT 1"
                + (" FOR SHARE" if current_read else ""),
                (family, f"case:{case_no}"[:191]),
            )
            row = cursor.fetchone()
        if not row or not row.get("result_snapshot"):
            return None
        raw = row["result_snapshot"]
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, dict) or (parsed.get("cleared") and not include_cleared):
            return None
        return parsed
    store = getattr(unit_of_work, "_helper_proposals", None)
    if isinstance(store, dict):
        parsed = store.get((family, case_no))
        if isinstance(parsed, dict) and (include_cleared or not parsed.get("cleared")):
            return parsed
    return None


def lock_group_postponement(unit_of_work: Any, case_no: str) -> None:
    """Serialize proposal replacement and a customer's decision for the same case."""
    repository = getattr(unit_of_work, "service_starts", None)
    if repository is not None:
        repository.lock_case(case_no)


def postponement_group_binding(unit_of_work: Any, case_no: str) -> LineOrderGroupBindingSnapshot | None:
    settings = unit_of_work.order_groups.get_invitation(case_no, lock=True)
    if settings and settings.binding.group_id and settings.binding.status in _ACTIVE_BINDING_STATUSES:
        return settings.binding
    return None


def require_postponement_assignment(
    app: Any, case_no: str, staff_id: int, assignment_id: int, dates: Sequence[LeaveDateChange], *,
    lock: bool = False,
) -> None:
    cases, _ = app.selected_leave_case(staff_id, case_no, lock=lock)
    assignment = next((item for item in cases if item.assignment_id == assignment_id), None)
    if assignment is None:
        raise ServiceStartConflict("leave_result_forbidden", "案件目前無法辦理延期，請重新開啟案件確認。")
    if any(str(item.original_date) not in assignment.service_dates for item in dates):
        raise ServiceStartConflict("leave_result_dates_changed", "原服務日已變更，請重新查詢排班。")


def latest_postponement_draft_revision(unit_of_work: Any, case_no: str) -> int:
    draft = load_latest_group_helper_proposal(unit_of_work, POSTPONEMENT_DRAFT_FAMILY, case_no, current_read=True)
    return draft["draft_revision"] if draft else 0


def postponement_proposal_ref(case_no: str, event_ref: str) -> str:
    return fingerprint_payload({"case_no": case_no, "event_ref": event_ref}).value[:32]


def postponement_group_message(case_no: str, draft_revision: int) -> str:
    return f"{_POSTPONEMENT_NOTICE_PREFIX}{case_no}-{draft_revision}"


def legacy_postponement_group_message(proposal_ref: str) -> str:
    return _POSTPONEMENT_SEND_PREFIX + proposal_ref

class LineGroupHelperApplication:
    """Coordinate step-5 case-group helper menu & workflows using strict Reply-only delivery."""

    def __init__(
        self,
        now: Callable[[], datetime] | None = None,
        *,
        service_start_factory: Callable[[Any], Any] | None = None,
        staff_schedule_url: Callable[[str, str], str] | None = None,
        aliases_provider: Callable[[], tuple[int, dict[str, list[str]]]] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._service_start_factory = service_start_factory
        self._staff_schedule_url = staff_schedule_url or _default_staff_schedule_url
        self._aliases_provider = aliases_provider or load_persisted_aliases

    def _business_today(self) -> date:
        return self._now().astimezone(_TAIPEI_TZ).date()

    def _aliases(self) -> dict[str, tuple[str, ...]]:
        _, routes = self._aliases_provider()
        return {
            "group_helper_menu": tuple(routes.get("group_helper_menu") or _DEFAULT_MENU_ALIASES),
            "group_postponement": tuple(routes.get("group_postponement") or _DEFAULT_POSTPONE_PREFIXES),
        }

    def handle_reply(self, inbox: Any, unit_of_work: Any) -> bool:
        return self.handle_message(inbox, unit_of_work)

    def handle_message(self, inbox: Any, unit_of_work: Any) -> bool:
        event = inbox.event
        if getattr(event.source, "source_type", None) is not LineSourceType.GROUP:
            return False
        group_id = _extract_group_id(event.source)
        user_id_obj = getattr(event.source, "user_id", None)
        user_id = getattr(user_id_obj, "value", None)
        if not group_id or not user_id:
            return False
        text = _message_text(inbox)
        if not text:
            return False

        aliases = self._aliases()
        is_menu_cmd = text in aliases["group_helper_menu"]
        postpone_match = _match_postponement_text(text, aliases["group_postponement"])
        saved_postpone_match = _POSTPONEMENT_SEND_RE.fullmatch(text)
        if not (is_menu_cmd or postpone_match or saved_postpone_match):
            return False

        ctx = self._resolve_group_context(
            unit_of_work, group_id, user_id, customer_audience_fallback=is_menu_cmd,
        )
        if ctx is None:
            return False
        if saved_postpone_match and saved_postpone_match.group("notice_revision") is not None:
            if saved_postpone_match.group("notice_case") != ctx["case_no"]:
                return False

        if is_menu_cmd:
            if not (ctx["is_staff"] or ctx["is_customer"] or ctx["is_admin"] or ctx.get("can_open_satisfaction_survey")):
                return False
            self._reply_helper_menu(inbox, unit_of_work, group_id, ctx)
            return True

        if postpone_match or saved_postpone_match:
            if not ctx["is_staff"]:
                self._reply_text(
                    inbox,
                    unit_of_work,
                    group_id,
                    "「雙方合意延期」功能僅供月嫂操作，由月嫂開啟選擇請假與補班日期",
                    "postpone-role-hint",
                )
                return True
            if saved_postpone_match:
                self._send_saved_postponement(
                    inbox, unit_of_work, group_id, ctx,
                    saved_postpone_match.group("proposal_ref"),
                    notice_revision=saved_postpone_match.group("notice_revision"),
                )
                return True
            raw_orig = [d.strip() for d in postpone_match.group(1).replace("、", ",").split(",") if d.strip()]
            raw_new = [d.strip() for d in postpone_match.group(2).replace("、", ",").split(",") if d.strip()]
            orig_days = [_iso_date_or_none(d) for d in raw_orig]
            new_days = [_iso_date_or_none(d) for d in raw_new]
            if not orig_days or not new_days or len(orig_days) != len(new_days) or any(d is None for d in orig_days + new_days):
                return False
            changes = [LeaveDateChange(o, n) for o, n in zip(orig_days, new_days)]  # type: ignore[arg-type]
            self._propose_postponement(
                inbox,
                unit_of_work,
                group_id,
                ctx,
                changes,
            )
            return True

        return False

    def handle_postback(self, inbox: Any, unit_of_work: Any) -> bool:
        data, params = _postback_info(inbox)
        if not data or not data.startswith(("group-helper:", "confirm-start:", "postponement:", "group-faq:")):
            return False
        event = inbox.event
        if getattr(event.source, "source_type", None) is not LineSourceType.GROUP:
            return True
        group_id = _extract_group_id(event.source)
        user_id_obj = getattr(event.source, "user_id", None)
        user_id = getattr(user_id_obj, "value", None)
        if not group_id or not user_id:
            return True

        ctx = self._resolve_group_context(
            unit_of_work, group_id, user_id,
            customer_audience_fallback=not data.startswith(("postponement:", "group-helper:mutual-postponement")),
        )
        if ctx is None:
            return True

        if data.startswith(f"{SATISFACTION_SURVEY_ACTION}:"):
            if data == f"{SATISFACTION_SURVEY_ACTION}:{ctx['case_no']}" and ctx.get("can_open_satisfaction_survey"):
                key = "helper-satisfaction-survey"
                payload = configured_payload(unit_of_work, key, {"type": "text", "text": HELPER_TEXT_DEFAULTS[key]})
                self._reply_text(inbox, unit_of_work, group_id, payload["text"], "satisfaction-survey")
            return True

        if data.startswith("group-helper:confirm-start-date"):
            self._handle_confirm_start_pick(inbox, unit_of_work, group_id, ctx, data, params)
            return True
        if data == "confirm-start:agree":
            self._handle_confirm_start_agree(inbox, unit_of_work, group_id, ctx)
            return True
        if data == "confirm-start:reselect":
            save_group_helper_proposal(
                unit_of_work, _FAMILY_START_PROPOSAL, ctx["case_no"], event.event_id.value, {"cleared": True}
            )
            role_label = (
                "工會專員"
                if ctx["is_admin"]
                else f"月嫂（{ctx['staff_name']}）"
                if ctx["is_staff"]
                else "客戶"
                if ctx["is_customer"]
                else "群組成員"
            )
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                f"{role_label}已取消本次提議，雙方可再次點選小幫手重新選擇日期。",
                "confirm-start-reselect",
            )
            return True
        if data == "group-helper:service-schedule":
            self._handle_service_schedule(inbox, unit_of_work, group_id, ctx)
            return True
        if data == "group-helper:case-information":
            self._handle_case_information(inbox, unit_of_work, group_id, ctx)
            return True
        if data.startswith("group-helper:mutual-postponement"):
            self._handle_mutual_postponement(inbox, unit_of_work, group_id, ctx, data)
            return True
        action, _, proposal_ref = data.removeprefix("postponement:").partition(":")
        if data.startswith("postponement:") and action == "agree":
            self._handle_postponement_agree(inbox, unit_of_work, group_id, ctx, proposal_ref)
            return True
        if data.startswith("postponement:") and action == "reject":
            if not (ctx["is_customer"] or ctx["is_staff"]):
                return True
            proposal = self._current_postponement_for_card(inbox, unit_of_work, group_id, ctx, proposal_ref)
            if proposal is None:
                return True
            if ctx["is_customer"]:
                action_text = "客戶已取消本次提議"
            else:
                actor_fingerprint = proposal.get("line_actor_fingerprint")
                if proposal["staff_id"] != ctx["staff_id"] or (
                    actor_fingerprint is not None
                    and actor_fingerprint != fingerprint_payload({"line_user_id": inbox.event.source.user_id.value}).value
                ):
                    return True
                action_text = "提案月嫂已撤回本次提議"
            self._clear_postponement(inbox, unit_of_work, ctx["case_no"])
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                f"{action_text}，原排程維持不變，雙方可再次點選小幫手重新選擇日期。",
                "postponement-reject",
            )
            return True
        if data == "group-helper:staff-assistance":
            self._reply_text(inbox, unit_of_work, group_id, GROUP_ASSISTANCE_DIRECTIONS, "staff-assistance-directions")
            return True
        if data == "group-helper:group-guidelines":
            payload = configured_payload(unit_of_work, "helper-guidelines-card", group_guidelines_card())
            self._reply_flex(inbox, unit_of_work, group_id, payload, "guidelines-card")
            return True
        if data.startswith("group-faq:"):
            topic = data.split(":", 1)[1].strip()
            key = f"helper-faq-{topic}"
            default_text = HELPER_TEXT_DEFAULTS.get(key)
            if default_text:
                payload = configured_payload(unit_of_work, key, {"type": "text", "text": default_text})
                self._reply_text(inbox, unit_of_work, group_id, payload["text"], f"faq-{topic}")
            return True

        return False

    def _resolve_group_context(
        self, unit_of_work: Any, group_id: str, user_id: str, *, customer_audience_fallback: bool,
    ) -> dict[str, Any] | None:
        loader = getattr(unit_of_work, "group_helper_context", None)
        binding_repo = getattr(unit_of_work, "order_groups", None)
        binding = None
        if binding_repo is not None:
            if hasattr(binding_repo, "get_by_group"):
                binding = binding_repo.get_by_group(group_id)
            elif hasattr(binding_repo, "get_by_group_id"):
                binding = binding_repo.get_by_group_id(group_id)
        if binding is None:
            return None
        status = getattr(binding, "status", None) or getattr(binding, "binding_status", None)
        if status not in _ACTIVE_BINDING_STATUSES and str(status) not in {s.value for s in _ACTIVE_BINDING_STATUSES}:
            return None
        case_no = str(binding.case_no)
        if callable(loader):
            return loader(case_no, user_id)

        conn = getattr(unit_of_work, "_connection", None)
        if conn is None:
            return None
        return self._load_mysql_context(
            conn, unit_of_work, case_no, user_id, customer_audience_fallback=customer_audience_fallback,
        )

    def _load_mysql_context(
        self, conn: Any, unit_of_work: Any, case_no: str, user_id: str, *, customer_audience_fallback: bool = True,
    ) -> dict[str, Any] | None:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no,o.status,o.start_date,o.actual_start_date,o.actual_end_date,"
                "o.service_days,o.lifecycle_version,o.client_id,c.service_type,c.name AS client_name "
                "FROM orders o LEFT JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s",
                (case_no,),
            )
            order = cursor.fetchone()
            if not order:
                return None

            cursor.execute(
                "SELECT a.id AS assignment_id,a.staff_id,s.name AS staff_name,g.aggregate_version AS scheduling_version "
                "FROM case_staff_assignments a "
                "JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id "
                "JOIN staff s ON s.id=a.staff_id "
                "WHERE a.case_no=%s ORDER BY a.assignment_sequence,a.id",
                (case_no,),
            )
            formal_rows = list(cursor.fetchall() or ())

            cursor.execute(
                "SELECT ps.id AS segment_id,ps.staff_id,s.name AS staff_name,ps.assigned_start_date "
                "FROM caregiver_matching_plans p "
                "JOIN caregiver_matching_plan_segments ps ON ps.plan_id=p.id "
                "JOIN staff s ON s.id=ps.staff_id "
                "WHERE p.case_no=%s AND p.is_active=1 ORDER BY ps.segment_order,ps.id",
                (case_no,),
            )
            segment_rows = list(cursor.fetchall() or ())

            cursor.execute(
                "SELECT 1 FROM scheduling_service_start_requests "
                "WHERE case_no=%s AND status='applied' "
                "AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(execution_dates,'$.kind')),'')='' LIMIT 1",
                (case_no,),
            )
            has_applied_start = cursor.fetchone() is not None

            cursor.execute(
                "SELECT day.work_date,day.is_work_day,a.staff_id,s.name AS staff_name FROM staff_schedule day "
                "JOIN case_staff_assignments a ON a.id=day.assignment_id "
                "LEFT JOIN staff s ON s.id=a.staff_id "
                "JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id "
                "WHERE a.case_no=%s AND day.effective_marker=1 ORDER BY day.work_date",
                (case_no,),
            )
            schedule_rows = list(cursor.fetchall() or ())

            cursor.execute(
                "SELECT subject_type,subject_reference FROM line_identity_role_bindings "
                "WHERE line_user_id=%s AND binding_status='bound'",
                (user_id,),
            )
            bindings = list(cursor.fetchall() or ())

        all_staff_assignments = formal_rows or segment_rows
        assigned_staff_ids = {str(r["staff_id"]) for r in all_staff_assignments}
        all_staff_names = list(dict.fromkeys(str(r.get("staff_name") or "").strip() for r in all_staff_assignments if r.get("staff_name")))
        combined_staff_name = "、".join(all_staff_names) or "指派月嫂"

        matched_staff_id = None
        for b in bindings:
            if b.get("subject_type") == "staff" and str(b.get("subject_reference")) in assigned_staff_ids:
                matched_staff_id = int(b.get("subject_reference"))
                break
        if matched_staff_id is None and getattr(unit_of_work, "customer_service", None) is not None:
            sub = unit_of_work.customer_service.staff_subject(user_id)
            if sub and str(sub.get("staff_id")) in assigned_staff_ids:
                matched_staff_id = int(sub["staff_id"])

        is_staff = matched_staff_id is not None
        user_formal = next((r for r in formal_rows if matched_staff_id and int(r["staff_id"]) == matched_staff_id), None) or (formal_rows[0] if formal_rows else None)
        user_segment = next((r for r in segment_rows if matched_staff_id and int(r["staff_id"]) == matched_staff_id), None) or (segment_rows[0] if segment_rows else None)

        staff_id = matched_staff_id or int((user_formal or user_segment or {}).get("staff_id") or 0) or None
        staff_name = combined_staff_name
        actual_start = _iso_date_or_none(order.get("actual_start_date"))
        planned_start = (
            actual_start
            or _iso_date_or_none((user_segment or {}).get("assigned_start_date"))
            or _iso_date_or_none(order.get("start_date"))
            or self._business_today()
        )
        has_schedule_rows = any(r.get("is_work_day") for r in schedule_rows)
        has_confirmed_start = bool(
            has_applied_start
            or (actual_start is not None and has_schedule_rows)
        )
        today = self._business_today()
        # 消失條件：改成實際服務日開始後才隱藏（today >= actual_start 且已排定或服務中）
        service_commenced = bool(
            order.get("status") == "服務中"
            or (has_confirmed_start and actual_start is not None and today >= actual_start)
        )

        is_admin = any(b.get("subject_type") == "admin" for b in bindings)
        admin_ref = next((b.get("subject_reference") for b in bindings if b.get("subject_type") == "admin"), None)
        admin_user_id = int(admin_ref) if isinstance(admin_ref, str) and admin_ref.isdigit() else None
        if not is_staff:
            is_staff = any(
                b.get("subject_type") == "staff" and (staff_id is None or str(b.get("subject_reference")) == str(staff_id))
                for b in bindings
            )
        if not is_staff and getattr(unit_of_work, "customer_service", None) is not None:
            sub = unit_of_work.customer_service.staff_subject(user_id)
            is_staff = bool(sub and (staff_id is None or int(sub["staff_id"]) == staff_id))

        scheduled_staff_ids = {str(row["staff_id"]) for row in schedule_rows if row.get("is_work_day")}
        can_open_satisfaction_survey = order.get("status") == OrderLifecycleStatus.COMPLETED and any(
            binding.get("subject_type") == "staff" and str(binding.get("subject_reference")) in scheduled_staff_ids
            for binding in bindings
        )

        client_id = order.get("client_id")
        is_customer = any(
            b.get("subject_type") == "customer"
            and (client_id is None or str(b.get("subject_reference")) == str(client_id))
            for b in bindings
        )
        if customer_audience_fallback and not is_customer and getattr(unit_of_work, "order_audiences", None) is not None:
            try:
                audience = unit_of_work.order_audiences.get(case_no)
            except (LookupError, RuntimeError):
                audience = None
            if audience is not None and getattr(audience, "customer_line_user_id", None) == LineUserId(user_id):
                is_customer = True

        return {
            "case_no": case_no,
            "order_status": order.get("status"),
            "order_version": int(order.get("lifecycle_version") or 0),
            "client_id": int(client_id) if client_id is not None else None,
            "client_name": str(order.get("client_name") or "").strip() or None,
            "service_days": int(order.get("service_days") or 20),
            "service_type": order.get("service_type"),
            "planned_start_date": planned_start,
            "actual_end_date": _iso_date_or_none(order.get("actual_end_date")),
            "staff_id": staff_id,
            "staff_name": staff_name,
            "segment_id": int(user_segment["segment_id"]) if user_segment and user_segment.get("segment_id") else None,
            "assignment_id": int(user_formal["assignment_id"]) if user_formal and user_formal.get("assignment_id") else None,
            "scheduling_version": int(user_formal["scheduling_version"]) if user_formal and user_formal.get("scheduling_version") is not None else 0,
            "is_started": has_confirmed_start,
            "has_confirmed_start": has_confirmed_start,
            "service_commenced": service_commenced,
            "schedule_rows": schedule_rows,
            "is_staff": is_staff,
            "can_open_satisfaction_survey": can_open_satisfaction_survey,
            "is_customer": is_customer,
            "is_admin": is_admin,
            "admin_user_id": admin_user_id,
        }

    def _service_start_app(self, unit_of_work: Any) -> Any | None:
        injected = getattr(unit_of_work, "service_start_workflow", None)
        if injected is not None:
            return injected
        conn = getattr(unit_of_work, "_connection", None)
        if self._service_start_factory is not None and conn is not None:
            return self._service_start_factory(conn)
        return None

    def _reply_helper_menu(self, inbox: Any, unit_of_work: Any, group_id: str, ctx: dict[str, Any]) -> None:
        case_no = ctx["case_no"]
        staff_name = ctx["staff_name"]
        payload = configured_payload(
            unit_of_work,
            "helper-menu-card",
            group_helper_menu_card(case_no, staff_name),
            {"case_no": case_no, "staff_name": staff_name},
        )
        card = render_group_helper_menu_state(
            payload,
            case_no=case_no,
            planned_start_date=str(ctx["planned_start_date"]),
            service_commenced=bool(ctx.get("service_commenced", ctx.get("is_started", False))),
            has_confirmed_start=bool(ctx.get("has_confirmed_start")),
            service_completed=ctx.get("order_status") == OrderLifecycleStatus.COMPLETED,
            show_satisfaction_survey=bool(ctx.get("can_open_satisfaction_survey")),
        )
        self._reply_flex(inbox, unit_of_work, group_id, card, "helper-menu")

    def _handle_confirm_start_pick(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        ctx: dict[str, Any],
        data: str,
        params: dict[str, Any],
    ) -> None:
        if not (ctx["is_staff"] or ctx["is_customer"] or ctx["is_admin"]):
            return
        if ctx.get("service_commenced", False):
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                "本案已於約定日期正式開工，如需調整排程請使用「雙方合意延期」。",
                "confirm-start-already-started",
            )
            return
        user_id_obj = getattr(inbox.event.source, "user_id", None)
        user_id = getattr(user_id_obj, "value", str(user_id_obj or ""))
        proposed_by = "admin" if ctx["is_admin"] else "staff" if ctx["is_staff"] else "customer"
        parts = data.split(":")
        picked = (
            _iso_date_or_none(params.get("date"))
            or (_iso_date_or_none(parts[2]) if len(parts) >= 3 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[-1]) else None)
            or ctx["planned_start_date"]
        )
        end_day = _compute_expected_end_date(picked, ctx["service_days"], ctx.get("service_type"))
        proposal = {
            "case_no": ctx["case_no"],
            "staff_id": ctx["staff_id"],
            "staff_name": ctx["staff_name"],
            "segment_id": ctx.get("segment_id"),
            "assignment_id": ctx.get("assignment_id"),
            "start_date": picked.isoformat(),
            "end_date": end_day.isoformat(),
            "proposed_by": proposed_by,
            "proposer_user_id": user_id,
        }
        save_group_helper_proposal(
            unit_of_work,
            _FAMILY_START_PROPOSAL,
            ctx["case_no"],
            inbox.event.event_id.value,
            proposal,
        )
        card = configured_payload(
            unit_of_work,
            "helper-confirm-start-card",
            confirm_start_date_card(
                ctx["case_no"],
                ctx["staff_name"],
                picked.isoformat(),
                end_day.isoformat(),
                proposed_by=proposed_by,
            ),
            {
                "case_no": ctx["case_no"],
                "staff_name": ctx["staff_name"],
                "start_date": picked.isoformat(),
                "end_date": end_day.isoformat(),
            },
        )
        if proposed_by != "staff" and isinstance(card.get("contents"), dict):
            bubble = card["contents"]
            header = bubble.get("header")
            if isinstance(header, dict) and isinstance(header.get("contents"), list):
                top_row = header["contents"][0].get("contents", []) if isinstance(header["contents"][0], dict) else []
                if top_row and isinstance(top_row[0], dict) and isinstance(top_row[0].get("contents"), list):
                    top_row[0]["contents"][0]["text"] = "客戶已發起" if proposed_by == "customer" else "工會已協調"
                if len(header["contents"]) > 2 and isinstance(header["contents"][2], dict):
                    header["contents"][2]["text"] = "客戶已選定日期，請月嫂確認" if proposed_by == "customer" else "工會專員已選定日期，請雙方確認"
            body = bubble.get("body")
            if isinstance(body, dict) and isinstance(body.get("contents"), list) and len(body["contents"]) >= 2:
                from subsystems.line.service_start_messages import _start_progress_card
                body["contents"][1] = _start_progress_card("雙方合意確認進度：", staff_name=ctx["staff_name"], proposed_by=proposed_by)
                if len(body["contents"]) >= 3 and isinstance(body["contents"][2], dict):
                    body["contents"][2]["text"] = (
                        "月嫂確認日期後系統將自動建立正式排程" if proposed_by == "customer" else "雙方同意後系統將自動建立正式排程"
                    )
        self._reply_flex(inbox, unit_of_work, group_id, card, "confirm-start-card")

    def _handle_confirm_start_agree(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        ctx: dict[str, Any],
    ) -> None:
        user_id_obj = getattr(inbox.event.source, "user_id", None)
        user_id = getattr(user_id_obj, "value", str(user_id_obj or ""))

        if ctx.get("service_commenced", False):
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                "本案開工日已完成確認並建立正式排班，可點選「服務排程」查看。",
                "confirm-start-already-done",
            )
            return

        proposal = load_latest_group_helper_proposal(unit_of_work, _FAMILY_START_PROPOSAL, ctx["case_no"])
        if not proposal or proposal.get("cleared") or not proposal.get("start_date"):
            return

        proposed_by = str(proposal.get("proposed_by") or "staff")
        proposer_user_id = str(proposal.get("proposer_user_id") or "")

        # 防呆規則：工會管理員有代確認權限；一般成員若自己提申請又按同意，或同角色按同意，保持安靜不反應以維護聊天室整潔
        if not ctx["is_admin"]:
            if proposer_user_id and user_id == proposer_user_id:
                return
            if proposed_by == "staff":
                if not ctx["is_customer"]:
                    return
            elif proposed_by == "customer":
                if not ctx["is_staff"]:
                    return
            else:
                if not (ctx["is_customer"] or ctx["is_staff"]):
                    return

        start_day = _iso_date_or_none(proposal["start_date"])
        if not ctx["staff_id"] or start_day is None:
            return

        app = self._service_start_app(unit_of_work)
        if app is None:
            raise RuntimeError("group_helper_service_start_workflow_missing")
        key = f"group-helper-start:{ctx['case_no']}:{inbox.event.event_id.value}"[:150]
        try:
            view = app.submit_in_current_unit_of_work(
                ServiceStartSubmission(
                    ctx["case_no"],
                    int(ctx["staff_id"]),
                    ctx.get("segment_id"),
                    ServiceStartDecision.ACCEPTED,
                    start_day,
                    int(ctx["order_version"]),
                    key,
                    assignment_id=ctx.get("assignment_id"),
                ),
                enqueue_group_schedule=False,
            )
        except ServiceStartConflict as error:
            self._reply_text(inbox, unit_of_work, group_id, f"開工確認未完成：{error.message}", "confirm-start-error")
            return

        if view.status == "substitute_required":
            save_group_helper_proposal(
                unit_of_work, _FAMILY_START_PROPOSAL, ctx["case_no"], inbox.event.event_id.value, {"cleared": True}
            )
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                f"⚠️ 案件 {ctx['case_no']} 偵測到月嫂排程檔期衝突，已為您轉交工會專員協助調整或安排代班。",
                "confirm-start-conflict",
            )
            return

        if view.status != "applied":
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                f"已收到案件 {ctx['case_no']} 開工確認，等候其他區段月嫂完成確認後將自動建立排班。",
                "confirm-start-awaiting",
            )
            return

        snapshot = view.result or {}
        actual_start = str(snapshot.get("actual_start_date") or start_day.isoformat())
        actual_end = str(
            snapshot.get("actual_end_date")
            or _compute_expected_end_date(start_day, ctx["service_days"], ctx.get("service_type")).isoformat()
        )
        save_group_helper_proposal(
            unit_of_work, _FAMILY_START_PROPOSAL, ctx["case_no"], inbox.event.event_id.value, {"cleared": True}
        )
        completed = configured_payload(
            unit_of_work,
            "helper-confirm-start-completed",
            {"type": "text", "text": HELPER_TEXT_DEFAULTS["helper-confirm-start-completed"]},
            {"case_no": ctx["case_no"], "start_date": actual_start, "end_date": actual_end},
        )
        self._reply_text(inbox, unit_of_work, group_id, completed["text"], "confirm-start-completed")

    def _handle_service_schedule(self, inbox: Any, unit_of_work: Any, group_id: str, ctx: dict[str, Any]) -> None:
        if not ctx["is_started"]:
            proposal = load_latest_group_helper_proposal(unit_of_work, _FAMILY_START_PROPOSAL, ctx["case_no"])
            planned_start = (
                _iso_date_or_none(proposal["start_date"])
                if proposal and proposal.get("start_date")
                else ctx["planned_start_date"]
            )
            planned_end = (
                _iso_date_or_none(proposal["end_date"])
                if proposal and proposal.get("end_date")
                else _compute_expected_end_date(planned_start, ctx["service_days"], ctx.get("service_type"))
            )
            payload = configured_payload(
                unit_of_work,
                "helper-schedule-unconfirmed",
                {"type": "text", "text": HELPER_TEXT_DEFAULTS["helper-schedule-unconfirmed"]},
                {
                    "case_no": ctx["case_no"],
                    "start_date": planned_start.isoformat(),
                    "end_date": planned_end.isoformat(),
                },
            )
            self._reply_text(inbox, unit_of_work, group_id, payload["text"], "schedule-unconfirmed")
            return

        schedule_rows = ctx.get("schedule_rows") or ()
        card = service_schedule_calendar_card(
            ctx["case_no"],
            schedule_rows,
            default_staff_name=ctx.get("staff_name") or "指派月嫂",
            today=self._business_today(),
        )
        self._reply_flex(inbox, unit_of_work, group_id, card, "service-schedule")

    def _handle_case_information(self, inbox: Any, unit_of_work: Any, group_id: str, ctx: dict[str, Any]) -> None:
        case_no = ctx["case_no"]
        staff_name = ctx["staff_name"]
        client_name = ctx.get("client_name")
        sections = self._load_case_information_sections(unit_of_work, ctx)
        conn = getattr(unit_of_work, "_connection", None)
        bank_account_info = None
        try:
            from subsystems.line.service_start_messages import resolve_case_bank_account_info
            if conn is not None:
                with conn.cursor() as cur:
                    bank_account_info = resolve_case_bank_account_info(cur, case_no)
            else:
                bank_account_info = resolve_case_bank_account_info(None, case_no)
        except Exception:
            bank_account_info = None
        card = configured_payload(
            unit_of_work,
            "helper-case-information-card",
            case_information_card(case_no, staff_name, sections, client_name=client_name, bank_account_info=bank_account_info),
            {"case_no": case_no, "staff_name": staff_name},
        )
        self._reply_flex(inbox, unit_of_work, group_id, card, "case-information")

    def _load_case_information_sections(self, unit_of_work: Any, ctx: dict[str, Any]) -> Sequence[Any]:
        if "order_information_sections" in ctx:
            return ctx["order_information_sections"]

        repo = getattr(unit_of_work, "order_information", None)
        if repo is not None and hasattr(repo, "load_owner_snapshot"):
            snapshot = repo.load_owner_snapshot(ctx["case_no"], ctx.get("assignment_id"))
            if snapshot is not None:
                from subsystems.orders.order_information import build_formal_information_sections
                facts = dict(snapshot.facts)
                if ctx.get("staff_name"):
                    facts["staff_name"] = ctx["staff_name"]
                return build_formal_information_sections(1, facts, snapshot.field_issues)

        conn = getattr(unit_of_work, "_connection", None)
        if conn is not None:
            from infrastructure.mysql.order_information_repository import MySqlOrderInformationRepository
            from subsystems.orders.order_information import build_formal_information_sections

            mysql_repo = MySqlOrderInformationRepository(conn)
            snapshot = mysql_repo.load_owner_snapshot(ctx["case_no"], ctx.get("assignment_id"))
            if snapshot is not None:
                facts = dict(snapshot.facts)
                if ctx.get("staff_name"):
                    facts["staff_name"] = ctx["staff_name"]
                return build_formal_information_sections(1, facts, snapshot.field_issues)

            try:
                from infrastructure.mysql.order_information_repository import (
                    _CASE_SQL, _apply_explicit_rate_correction, _facts, _merge_contract_payment_facts
                )
                from collections.abc import Mapping
                with conn.cursor() as cursor:
                    cursor.execute(_CASE_SQL, (ctx["case_no"],))
                    case = cursor.fetchone()
                    if isinstance(case, Mapping):
                        case = _apply_explicit_rate_correction(cursor, case, ctx["case_no"])
                        facts, issues = _facts(case, {
                            "assigned_start_date": case.get("planned_start_date") or ctx.get("planned_start_date"),
                            "assigned_end_date": case.get("planned_end_date") or ctx.get("actual_end_date"),
                            "staff_name": ctx.get("staff_name"),
                        })
                        _merge_contract_payment_facts(conn, ctx["case_no"], facts, use_current_order_payments=True)
                        return build_formal_information_sections(1, facts, issues)
            except Exception:
                pass

        return ()

    def _handle_mutual_postponement(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        ctx: dict[str, Any],
        data: str,
    ) -> None:
        if not ctx["is_staff"]:
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                "「雙方合意延期」功能僅供月嫂操作，由月嫂開啟選擇請假與補班日期",
                "postpone-role-hint",
            )
            return

        parts = data.split(":")
        if len(parts) == 4:
            orig_day = _iso_date_or_none(parts[2])
            new_day = _iso_date_or_none(parts[3])
            if orig_day and new_day:
                self._propose_postponement(
                    inbox, unit_of_work, group_id, ctx, [LeaveDateChange(orig_day, new_day)]
                )
                return

        liff_url = self._staff_schedule_url(ctx["case_no"], "postpone")
        card = mutual_postponement_entry_card(ctx["case_no"], liff_url)
        self._reply_flex(inbox, unit_of_work, group_id, card, "postpone-liff-link")

    def _propose_postponement(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        ctx: dict[str, Any],
        changes: list[LeaveDateChange],
    ) -> None:
        if not ctx["staff_id"] or not ctx.get("assignment_id"):
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                "本案尚未建立正式服務排班，尚無法辦理合意延期補班；如需調整開工日請直接於選單選擇「確認開工日」。",
                "postpone-no-assignment",
            )
            return

        case_no = ctx["case_no"]
        lock_group_postponement(unit_of_work, case_no)
        binding = postponement_group_binding(unit_of_work, case_no)
        if binding is None or binding.group_id.value != group_id:
            return
        app = self._service_start_app(unit_of_work)
        try:
            require_postponement_assignment(
                app, case_no, int(ctx["staff_id"]), int(ctx["assignment_id"]), changes, lock=True,
            )
            preview = app.arrangement.preview_leave_defer(
                case_no, int(ctx["staff_id"]), int(ctx["assignment_id"]), tuple(changes),
            )
        except ServiceStartConflict as error:
            self._reply_text(
                inbox, unit_of_work, group_id, f"⚠️ 檔期檢核未通過：{error.message}", "postpone-preview-invalid",
            )
            return
        if preview.get("conflict"):
            self._reply_text(
                inbox, unit_of_work, group_id,
                f"⚠️ {preview.get('message', '此補班日已有檔期衝突，請重新與客戶協調其他日期！')}",
                "postpone-conflict",
            )
            return

        leave_start_label = "、".join(str(item.original_date) for item in changes)
        leave_end_label = "、".join(str(item.new_date) for item in changes)
        event_id = inbox.event.event_id.value
        proposal = {
            "case_no": ctx["case_no"],
            "staff_id": ctx["staff_id"],
            "assignment_id": ctx["assignment_id"],
            "proposal_ref": postponement_proposal_ref(ctx["case_no"], event_id),
            "draft_revision": latest_postponement_draft_revision(unit_of_work, case_no),
            "group_binding_version": binding.version.value,
            "line_actor_fingerprint": fingerprint_payload({"line_user_id": inbox.event.source.user_id.value}).value,
            "dates": [{"original_date": str(c.original_date), "new_date": str(c.new_date)} for c in changes],
            "leave_start_date": leave_start_label,
            "leave_end_date": leave_end_label,
        }
        proposal = save_group_helper_proposal(
            unit_of_work,
            _FAMILY_POSTPONE_PROPOSAL,
            ctx["case_no"],
            event_id,
            proposal,
        )
        self._reply_postponement_card(inbox, unit_of_work, group_id, ctx, proposal)

    def _send_saved_postponement(self, inbox, unit_of_work, group_id, ctx, proposal_ref, *, notice_revision=None):
        case_no = ctx["case_no"]
        lock_group_postponement(unit_of_work, case_no)
        binding = postponement_group_binding(unit_of_work, case_no)
        if binding is None or binding.group_id.value != group_id:
            return
        if notice_revision is not None:
            notice = load_group_helper_proposal(
                unit_of_work, POSTPONEMENT_NOTICE_FAMILY, case_no, notice_revision, current_read=True,
            )
            if notice is None:
                return
            proposal_ref = notice["proposal_ref"]
        draft = load_group_helper_proposal(
            unit_of_work, POSTPONEMENT_DRAFT_FAMILY, case_no, proposal_ref, current_read=True,
        )
        if draft is not None:
            if (
                draft["staff_id"] != ctx["staff_id"]
                or draft["line_actor_fingerprint"] != fingerprint_payload({"line_user_id": inbox.event.source.user_id.value}).value
                or draft["group_binding_version"] != binding.version.value
            ):
                return
        previous = load_latest_group_helper_proposal(
            unit_of_work, _FAMILY_POSTPONE_PROPOSAL, case_no, current_read=True, include_cleared=True,
        ) or {}
        if load_group_helper_proposal(unit_of_work, _FAMILY_POSTPONE_CARD, case_no, proposal_ref, current_read=True):
            return
        if draft is not None:
            if draft["draft_revision"] <= previous.get("draft_revision", 0):
                self._reply_text(
                    inbox, unit_of_work, group_id,
                    "這筆延期提案已失效，請重新開啟延期申請並核對日期。",
                    "postpone-stale-draft",
                )
                return
            dates = tuple(
                LeaveDateChange(date.fromisoformat(item["original_date"]), date.fromisoformat(item["new_date"]))
                for item in draft["dates"]
            )
            try:
                require_postponement_assignment(
                    self._service_start_app(unit_of_work), case_no, draft["staff_id"], draft["assignment_id"],
                    dates, lock=True,
                )
            except ServiceStartConflict as error:
                self._reply_text(inbox, unit_of_work, group_id, error.message, "postpone-preview-invalid")
                return
            proposal = save_group_helper_proposal(
                unit_of_work, _FAMILY_POSTPONE_PROPOSAL, case_no, proposal_ref, draft,
            )
        elif (
            notice_revision is None and previous.get("proposal_ref") == proposal_ref
            and previous.get("staff_id") == ctx["staff_id"]
        ):
            proposal = previous
        else:
            return
        save_group_helper_proposal(
            unit_of_work, _FAMILY_POSTPONE_CARD, case_no, proposal_ref,
            {"group_event": inbox.event.event_id.value},
        )
        self._reply_postponement_card(inbox, unit_of_work, group_id, ctx, proposal)

    def _current_postponement_for_card(self, inbox, unit_of_work, group_id, ctx, proposal_ref):
        lock_group_postponement(unit_of_work, ctx["case_no"])
        proposal = load_latest_group_helper_proposal(
            unit_of_work, _FAMILY_POSTPONE_PROPOSAL, ctx["case_no"], current_read=True,
        )
        if proposal_ref and proposal and proposal.get("dates") and proposal.get("proposal_ref") == proposal_ref:
            if "group_binding_version" not in proposal:
                return proposal
            binding = postponement_group_binding(unit_of_work, ctx["case_no"])
            if binding and binding.group_id.value == group_id and binding.version.value == proposal["group_binding_version"]:
                return proposal
        self._reply_text(
            inbox, unit_of_work, group_id,
            "這張延期確認單已失效。請使用原群組最新的確認單，或請月嫂重新送出。",
            "postpone-stale-card",
        )
        return None

    def _clear_postponement(self, inbox, unit_of_work, case_no):
        save_group_helper_proposal(
            unit_of_work, _FAMILY_POSTPONE_PROPOSAL, case_no, inbox.event.event_id.value,
            {"cleared": True, "draft_revision": latest_postponement_draft_revision(unit_of_work, case_no)},
        )

    def _reply_postponement_card(self, inbox, unit_of_work, group_id, ctx, proposal):
        leave_start_label = proposal["leave_start_date"]
        leave_end_label = proposal["leave_end_date"]
        card = configured_payload(
            unit_of_work,
            "helper-postponement-card",
            mutual_postponement_card(
                ctx["case_no"], ctx["staff_name"], leave_start_label, leave_end_label,
                proposal_ref=proposal["proposal_ref"],
            ),
            {
                "case_no": ctx["case_no"],
                "staff_name": ctx["staff_name"],
                "leave_start_date": leave_start_label,
                "leave_end_date": leave_end_label,
            },
        )
        self._reply_flex(inbox, unit_of_work, group_id, card, "postponement-card")

    def _handle_postponement_agree(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        ctx: dict[str, Any],
        proposal_ref: str,
    ) -> None:
        if ctx.get("is_staff"):
            return
        if not ctx["is_customer"]:
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                "請由客戶本人點選「同意延期補班」完成雙方確認。",
                "postpone-need-customer",
            )
            return
        proposal = self._current_postponement_for_card(inbox, unit_of_work, group_id, ctx, proposal_ref)
        if proposal is None:
            return

        changes = tuple(
            LeaveDateChange(date.fromisoformat(d["original_date"]), date.fromisoformat(d["new_date"]))
            for d in proposal["dates"]
        )
        app = self._service_start_app(unit_of_work)
        if app is None:
            raise RuntimeError("group_helper_service_start_workflow_missing")
        key = f"group-helper-postpone:{ctx['case_no']}:{inbox.event.event_id.value}"[:150]
        try:
            view = app.submit_leave_in_current_unit_of_work(
                LeaveResultSubmission(
                    ctx["case_no"],
                    int(proposal["staff_id"]),
                    int(proposal["assignment_id"]),
                    "defer",
                    changes,
                    int(ctx["order_version"]),
                    int(ctx["scheduling_version"]),
                    key,
                ),
                enqueue_group_schedule=False,
            )
        except ServiceStartConflict as error:
            self._reply_text(inbox, unit_of_work, group_id, f"延期補班未完成：{error.message}", "postpone-error")
            return

        self._clear_postponement(inbox, unit_of_work, ctx["case_no"])
        if view.status == "substitute_required":
            self._reply_text(
                inbox,
                unit_of_work,
                group_id,
                "⚠️ 偵測到月嫂該日檔期衝突，原排班與補助天數尚未變更；請重新與月嫂協調其他補班日期，或由工會協助。",
                "postpone-apply-conflict",
            )
            return

        completed = configured_payload(
            unit_of_work,
            "helper-postponement-completed",
            {"type": "text", "text": HELPER_TEXT_DEFAULTS["helper-postponement-completed"]},
            {
                "case_no": ctx["case_no"],
                "leave_start_date": proposal["leave_start_date"],
                "leave_end_date": proposal["leave_end_date"],
            },
        )
        self._reply_text(inbox, unit_of_work, group_id, completed["text"], "postpone-completed")

    def _reply_text(self, inbox: Any, unit_of_work: Any, group_id: str, text: str, tag: str) -> None:
        self._enqueue_reply(
            inbox,
            unit_of_work,
            group_id,
            LineMessageKind.TEXT,
            canonical_line_payload_json({"type": "text", "text": text}),
            tag,
        )

    def _reply_flex(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        payload: dict[str, Any],
        tag: str,
    ) -> None:
        self._enqueue_reply(
            inbox,
            unit_of_work,
            group_id,
            LineMessageKind.FLEX,
            canonical_line_payload_json(payload),
            tag,
        )

    def _enqueue_reply(
        self,
        inbox: Any,
        unit_of_work: Any,
        group_id: str,
        kind: LineMessageKind,
        payload_json: str,
        tag: str,
    ) -> None:
        event_id = inbox.event.event_id.value
        key = IdempotencyKey(f"group-helper:{event_id}:{tag}"[:191])
        unit_of_work.delivery_tasks.enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.GROUP, LineGroupId(group_id)),
                kind,
                payload_json,
                inbox.event.occurred_at,
                key,
                CorrelationId(f"line-event:{event_id}"),
                REPLY_ONLY_WEBHOOK_SOURCE,
                event_id,
            )
        )


__all__ = [
    "LineGroupHelperApplication",
    "load_latest_group_helper_proposal",
    "save_group_helper_proposal",
]
