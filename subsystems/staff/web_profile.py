from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from datetime import date
from typing import Protocol
from uuid import UUID

from domains.staff.web_profile import (
    PublishedWebProfilePhoto,
    WebProfileCategory,
    WebProfileConflict,
    WebProfileEntryVersion,
    WebProfileFolder,
    WebProfileFolderFile,
    WebProfilePhoto,
    WebProfileTemplateItem,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from subsystems.controlled_files.workflow import (
    ApplyControlledFile,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileWorkflow,
    ControlledFileWorkflowError,
    StageControlledFile,
)


class WebProfileRepository(Protocol):
    def templates(self) -> tuple[WebProfileTemplateItem, ...]: ...
    def template(self, item_id: int, *, lock: bool = False) -> WebProfileTemplateItem | None: ...
    def save_template(self, item: WebProfileTemplateItem, actor: str) -> WebProfileTemplateItem: ...
    def staff_name(self, staff_id: int, *, lock: bool = False) -> str | None: ...
    def current(self, staff_id: int) -> tuple[PublishedWebProfilePhoto, ...]: ...
    def other_current(self, staff_id: int, item_id: int, *, lock: bool) -> PublishedWebProfilePhoto | None: ...
    def entry(self, staff_id: int, entry_id: int, *, lock: bool = False) -> PublishedWebProfilePhoto | None: ...
    def has_multiple_active_entries(self, item_id: int) -> bool: ...
    def removed(self, staff_id: int, item_id: int, expected: WebProfileEntryVersion) -> bool: ...
    def remove(self, staff_id: int, item_id: int, expected: WebProfileEntryVersion, actor: str) -> None: ...
    def original_used(self, file_id: str, *, lock: bool) -> bool: ...
    def publish(self, staff_id: int, photo: WebProfilePhoto, actor: str) -> PublishedWebProfilePhoto: ...
    def approval(
        self, operation_id: UUID, staff_id: int, *, lock: bool = False, command: dict | None = None,
    ) -> tuple[dict, ...] | None: ...
    def record_approval(
        self, operation_id: UUID, staff_id: int, results: tuple[dict, ...], *, command: dict | None = None,
    ) -> None: ...


_OWNER = ControlledFileOwner.STAFF
_PURPOSE = ControlledFilePurpose.STAFF_PROFILE_PHOTO
_ORIGINALS = "staff-web/original"
_CROPS = "staff-web/crop"


class StaffWebProfile:
    def __init__(
        self,
        repository: WebProfileRepository,
        files: Callable[[], ControlledFileWorkflow],
        uow: Callable[[], UnitOfWork],
        *,
        registration_uow: Callable[[], UnitOfWork] | None = None,
    ) -> None:
        self.repository = repository
        self._files = files
        self._uow = uow
        self._registration_uow = uow if registration_uow is None else registration_uow

    def save_template(self, item: WebProfileTemplateItem, actor: ActorContext) -> WebProfileTemplateItem:
        with self._uow() as uow:
            if item.item_id is not None:
                current = self.repository.template(item.item_id, lock=True)
                if current is None or current.version != item.version:
                    raise WebProfileConflict("staff_web_template_stale")
                if (
                    item.category is WebProfileCategory.OTHER and current.category is not item.category
                    and self.repository.has_multiple_active_entries(item.item_id)
                ):
                    raise WebProfileConflict("staff_web_template_other_has_multiple")
            saved = self.repository.save_template(item, actor.actor_id)
            uow.commit()
        return saved

    def self_service(self, staff_id: int) -> dict:
        return {"templates": self.repository.templates(), "published": self.repository.current(staff_id)}

    def prepare(self, staff_id: int, photos: Sequence[WebProfilePhoto]) -> tuple[WebProfilePhoto, ...]:
        return self._validate_batch(staff_id, photos, lock=False)

    def _validate_batch(
        self, staff_id: int, photos: Sequence[WebProfilePhoto], *, lock: bool, admin_upload: bool = False,
    ) -> tuple[WebProfilePhoto, ...]:
        originals = {photo.original_file_id for photo in photos}
        replacements = [photo.entry_id for photo in photos if photo.entry_id is not None]
        if len(originals) != len(photos) or len(set(replacements)) != len(replacements):
            raise ValueError("staff_web_duplicate_photo")
        other_items: set[int] = set()
        return tuple(self._validate(staff_id, photo, other_items, lock=lock, admin_upload=admin_upload) for photo in photos)

    def apply_in_current_uow(
        self, staff_id: int, photos: Sequence[WebProfilePhoto], operation_id: UUID, actor: ActorContext,
    ) -> tuple[dict, ...]:
        return self._apply(staff_id, photos, operation_id, actor, command=None)

    def _apply(
        self, staff_id: int, photos: Sequence[WebProfilePhoto], operation_id: UUID, actor: ActorContext,
        *, command: dict | None,
    ) -> tuple[dict, ...]:
        if self.repository.staff_name(staff_id, lock=True) is None:
            raise LookupError("staff_web_staff_not_found")
        prior = self.repository.approval(operation_id, staff_id, lock=True, command=command)
        if prior is not None:
            return prior
        results = []
        ordered = sorted(photos, key=lambda row: row.template_item_id)
        for checked in self._validate_batch(staff_id, ordered, lock=True, admin_upload=command is not None):
            publication = self.repository.publish(staff_id, checked, actor.actor_id)
            results.append({
                "entry_id": publication.entry_id, "version": publication.version,
                "template_item_id": checked.template_item_id, "file_id": publication.file_id,
            })
        saved = tuple(results)
        self.repository.record_approval(operation_id, staff_id, saved, command=command)
        return saved

    def _validate(
        self, staff_id: int, photo: WebProfilePhoto, other_items: set[int], *, lock: bool, admin_upload: bool,
    ) -> WebProfilePhoto:
        template = self.repository.template(photo.template_item_id, lock=lock)
        if template is None:
            raise ValueError("staff_web_template_not_found")
        if photo.template_version != template.version:
            raise WebProfileConflict("staff_web_template_stale")
        expiry = template.expiry_for_submission(photo.expiry_date)
        if expiry and expiry.year < 1000:
            raise ValueError("staff_web_expiry_invalid")
        if (photo.entry_id is None) != (photo.entry_version is None):
            raise ValueError("staff_web_replacement_invalid")
        if template.category is WebProfileCategory.OTHER:
            if photo.template_item_id in other_items:
                raise ValueError("staff_web_other_single_photo")
            other_items.add(photo.template_item_id)
            current = self.repository.other_current(staff_id, photo.template_item_id, lock=lock)
            actual = (current.entry_id, current.version) if current else (None, None)
            if actual != (photo.entry_id, photo.entry_version):
                raise WebProfileConflict("staff_web_publication_stale")
        elif photo.entry_id is not None:
            if admin_upload:
                raise ValueError("staff_web_replacement_invalid")
            current = self.repository.entry(staff_id, photo.entry_id, lock=lock)
            if current is None or current.item.item_id != photo.template_item_id or current.version != photo.entry_version:
                raise WebProfileConflict("staff_web_publication_stale")
        self._owned_file(staff_id, photo.original_file_id, _ORIGINALS)
        if self.repository.original_used(photo.original_file_id, lock=lock):
            raise WebProfileConflict("staff_web_original_already_published")
        if photo.crop_file_id is not None:
            self._owned_file(staff_id, photo.crop_file_id, f"{_CROPS}/{photo.original_file_id}")
        return replace(photo, expiry_date=expiry)

    def folders(self, staff_id: int) -> tuple[WebProfileFolder, ...]:
        if self.repository.staff_name(staff_id) is None:
            raise LookupError("staff_web_staff_not_found")
        templates = self.repository.templates()
        grouped: dict[int, list[WebProfileFolderFile]] = {}
        for photo in self.repository.current(staff_id):
            item_id = photo.item.item_id
            if item_id is None:
                raise RuntimeError("staff_web_publication_template_missing")
            file = self._files().readback(photo.original_file_id)
            grouped.setdefault(item_id, []).append(WebProfileFolderFile(
                photo.entry_id, photo.version, file.filename,
                photo.expiry_date if photo.item.category.requires_expiry else None,
            ))
        return tuple(WebProfileFolder(
            template.item_id, template.version, template.name, template.category, tuple(grouped.get(template.item_id, ())),
        ) for template in templates if template.item_id is not None)

    def publish_uploaded(
        self, staff_id: int, photos: Sequence[WebProfilePhoto], operation_id: UUID, actor: ActorContext,
    ) -> tuple[WebProfileEntryVersion, ...]:
        command = {"admin_publication": [encode_web_photo(photo) for photo in photos]}
        with self._uow() as uow:
            results = self._apply(staff_id, photos, operation_id, actor, command=command)
            uow.commit()
        return tuple(WebProfileEntryVersion(result["entry_id"], result["version"]) for result in results)

    def remove_publication(
        self, staff_id: int, item_id: int, template_version: int, expected: WebProfileEntryVersion, actor: ActorContext,
    ) -> None:
        with self._uow() as uow:
            if self.repository.staff_name(staff_id, lock=True) is None:
                raise LookupError("staff_web_staff_not_found")
            template = self.repository.template(item_id, lock=True)
            if template is None or template.version != template_version:
                raise WebProfileConflict("staff_web_template_stale")
            if self.repository.removed(staff_id, item_id, expected):
                return
            if template.category is WebProfileCategory.OTHER:
                current = self.repository.other_current(staff_id, item_id, lock=True)
            else:
                current = self.repository.entry(staff_id, expected.entry_id, lock=True)
            if (
                current is None or current.item.item_id != item_id
                or (current.entry_id, current.version) != (expected.entry_id, expected.entry_version)
            ):
                raise WebProfileConflict("staff_web_publication_stale")
            self.repository.remove(staff_id, item_id, expected, actor.actor_id)
            if not self.repository.removed(staff_id, item_id, expected):
                raise RuntimeError("staff_web_removal_readback_missing")
            uow.commit()

    def upload_original(self, staff_id: int, upload_id: UUID, filename: str, mime: str, data: bytes) -> str:
        return self._store(
            staff_id, f"original-{upload_id.hex}", _ORIGINALS, filename, mime, data,
            ActorContext(f"staff:{staff_id}"),
        )

    def upload_for_staff(
        self, staff_id: int, upload_id: UUID, filename: str, mime: str, data: bytes, actor: ActorContext,
    ) -> ControlledFileReadback:
        if self.repository.staff_name(staff_id) is None:
            raise LookupError("staff_web_staff_not_found")
        file_id = self._store(staff_id, f"admin-original-{upload_id.hex}", _ORIGINALS, filename, mime, data, actor)
        return self._files().readback(file_id)

    def save_crop(
        self, staff_id: int, original_id: str, crop_id: UUID,
        filename: str, mime: str, data: bytes, actor: ActorContext,
    ) -> str:
        self._owned_file(staff_id, original_id, _ORIGINALS)
        return self._store(
            staff_id, f"crop-{original_id}-{crop_id.hex}", f"{_CROPS}/{original_id}",
            filename, mime, data, actor,
        )

    def pending_image(self, staff_id: int, photo: WebProfilePhoto, *, original: bool):
        if original or photo.crop_file_id is None:
            file_id, folder = photo.original_file_id, _ORIGINALS
        else:
            file_id, folder = photo.crop_file_id, f"{_CROPS}/{photo.original_file_id}"
        self._owned_file(staff_id, file_id, folder)
        return self._files().download(file_id)

    def customer_page(self, staff_id: int) -> dict:
        name = self.repository.staff_name(staff_id)
        if name is None:
            raise LookupError("staff_web_staff_not_found")
        groups: dict[WebProfileCategory, list[dict]] = {category: [] for category in WebProfileCategory}
        for photo in self.repository.current(staff_id):
            groups[photo.item.category].append(
                {"item_name": photo.item.name, "image_entry": photo.entry_id, "image_version": photo.version}
            )
        return {"name": name, "groups": [
            {"category": category, "images": images} for category, images in groups.items() if images
        ]}

    def customer_image(self, staff_id: int, entry_id: int, version: int):
        published = self.repository.entry(staff_id, entry_id)
        if published is None or published.version != version:
            raise LookupError("staff_web_image_not_found")
        return self._files().download(published.file_id)

    def _owned_file(self, staff_id: int, file_id: str, folder: str) -> None:
        file = self._files().readback(file_id)
        if (
            file.owner != _OWNER or file.purpose != _PURPOSE
            or file.subject_reference != str(staff_id) or file.logical_folder != folder
        ):
            raise ValueError("staff_web_file_owner_mismatch")

    def _store(
        self, staff_id: int, object_key: str, folder: str, filename: str,
        mime: str, data: bytes, actor: ActorContext,
    ) -> str:
        files = self._files()
        key = f"staff-web:{staff_id}:{object_key}"
        correlation = CorrelationId(key)
        staged = files.stage(StageControlledFile(
            _OWNER, _PURPOSE, str(staff_id), object_key, folder, filename,
            mime, data, IdempotencyKey(f"{key}:stage"), actor, correlation,
        ))
        intent = ControlledFileIntent(staged.staging_id, _OWNER, _PURPOSE, str(staff_id), object_key, folder)
        with self._registration_uow() as uow:
            # Match publication's Staff-first order before locking staging or receipts.
            if self.repository.staff_name(staff_id, lock=True) is None:
                raise ControlledFileWorkflowError("owner_subject_not_found", "檔案目前無法受理。")
            previous = files.find_current_readback(_OWNER, _PURPOSE, str(staff_id), object_key)
            if previous is not None:
                if previous.sha256_digest != staged.sha256_digest:
                    raise WebProfileConflict("staff_web_upload_stale")
                return previous.file_id
            preview = files.preview(intent)
            if preview.blockers:
                raise ControlledFileWorkflowError(preview.blockers[0], "檔案目前無法受理。")
            receipt = files.apply_borrowed(ApplyControlledFile(
                intent, preview.expected_staging_version, preview.preview_fingerprint,
                IdempotencyKey(f"{key}:register"), actor, correlation,
            ))
            uow.commit()
            return receipt.readback.file_id


def encode_web_photo(photo: WebProfilePhoto) -> dict:
    fields = asdict(photo)
    fields["expiry_date"] = photo.expiry_date.isoformat() if photo.expiry_date else None
    return fields


def decode_web_photo(fields) -> WebProfilePhoto:
    values = dict(fields)
    if values.get("expiry_date") is not None:
        values["expiry_date"] = date.fromisoformat(values["expiry_date"])
    return WebProfilePhoto(**values)
