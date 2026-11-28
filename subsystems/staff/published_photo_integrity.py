from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from domains.staff.web_profile import PublishedWebProfilePhoto
from subsystems.controlled_files.contracts import ControlledFileStorageError
from subsystems.controlled_files.workflow import (
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
    ControlledFileWorkflow,
    ControlledFileWorkflowError,
)

STAFF_WEB_FILE_OWNER = ControlledFileOwner.STAFF
STAFF_WEB_FILE_PURPOSE = ControlledFilePurpose.STAFF_PROFILE_PHOTO
STAFF_WEB_ORIGINALS = "staff-web/original"
STAFF_WEB_CROPS = "staff-web/crop"

PhotoIntegrityStatus = Literal["ok", "missing", "mismatch", "unavailable"]


class PhotoIntegrityReason(StrEnum):
    VERIFIED = "verified"
    PAYLOAD_MISSING = "payload_missing"
    BYTES_MISMATCH = "bytes_mismatch"
    INVALID_IMAGE = "invalid_image"
    REFERENCE_MISMATCH = "reference_mismatch"
    READ_UNCONFIRMED = "read_unconfirmed"


_STATUS_BY_REASON: dict[PhotoIntegrityReason, PhotoIntegrityStatus] = {
    PhotoIntegrityReason.VERIFIED: "ok",
    PhotoIntegrityReason.PAYLOAD_MISSING: "missing",
    PhotoIntegrityReason.BYTES_MISMATCH: "mismatch",
    PhotoIntegrityReason.INVALID_IMAGE: "mismatch",
    PhotoIntegrityReason.REFERENCE_MISMATCH: "mismatch",
    PhotoIntegrityReason.READ_UNCONFIRMED: "unavailable",
}


@dataclass(frozen=True, slots=True)
class PublishedPhotoIntegrity:
    entry_id: int
    version: int
    reason: PhotoIntegrityReason

    @property
    def status(self) -> PhotoIntegrityStatus:
        return _STATUS_BY_REASON[self.reason]


def inspect_published_photo(
    photo: PublishedWebProfilePhoto,
    files: ControlledFileWorkflow,
    decode: Callable[[bytes], object],
) -> PublishedPhotoIntegrity:
    return PublishedPhotoIntegrity(photo.entry_id, photo.version, _reason(photo, files, decode))


def _reason(
    photo: PublishedWebProfilePhoto,
    files: ControlledFileWorkflow,
    decode: Callable[[bytes], object],
) -> PhotoIntegrityReason:
    folder = STAFF_WEB_ORIGINALS if photo.crop_file_id is None else f"{STAFF_WEB_CROPS}/{photo.original_file_id}"
    try:
        file = files.readback(photo.file_id)
        if not matches_staff_web_file(file, photo.staff_id, folder):
            return PhotoIntegrityReason.REFERENCE_MISMATCH
        content = files.download(photo.file_id)
    except ControlledFileStorageError as error:
        if error.code == "controlled_file_not_found":
            return PhotoIntegrityReason.PAYLOAD_MISSING
        if error.code == "controlled_file_staging_digest_mismatch":
            return PhotoIntegrityReason.BYTES_MISMATCH
        return PhotoIntegrityReason.READ_UNCONFIRMED
    except (ControlledFileWorkflowError, OSError):
        return PhotoIntegrityReason.READ_UNCONFIRMED

    if len(content.content) != file.size_bytes or content.content_sha256 != file.sha256_digest.lower():
        return PhotoIntegrityReason.BYTES_MISMATCH
    try:
        decode(content.content)
    except ValueError:
        return PhotoIntegrityReason.INVALID_IMAGE
    return PhotoIntegrityReason.VERIFIED


def matches_staff_web_file(file: ControlledFileReadback, staff_id: int, folder: str) -> bool:
    return (
        file.owner == STAFF_WEB_FILE_OWNER and file.purpose == STAFF_WEB_FILE_PURPOSE
        and file.subject_reference == str(staff_id) and file.logical_folder == folder
    )
