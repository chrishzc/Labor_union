from io import BytesIO
from pathlib import PureWindowsPath
from typing import Annotated
from unicodedata import category as unicode_category
from uuid import UUID
import warnings

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_line_matching_reader,
    require_registry_reader,
    require_registry_writer,
)
from api.dependencies.staff_profile_change import staff_profile_change_application, staff_profile_change_staging
from api.dependencies.staff_web_profile import staff_web_profile_application
from api.routes.line_staff_self_service import _verified_line_user_id
from api.routes.matches import matching_notifications
from api.routes.staff_profile_change import _bound_staff_id, _require_active, _review, _translate_errors
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import StaffLiffRequest
from api.schemas.staff_web_profile import (
    CropInput,
    CustomerWebProfileRequest,
    EntryVersionView,
    FoldersView,
    FolderView,
    PublicationInput,
    PublicationsView,
    PublishedWebProfilePreviewView,
    RemovedFileView,
    TemplateItemInput,
    UploadedPhotoView,
)
from domains.staff.web_profile import WebProfileConflict, WebProfileEntryVersion
from infrastructure.file.storage_layout import safe_filename_component
from infrastructure.runtime.file_transfer_settings import file_transfer_settings
from subsystems.staff.web_profile import StaffWebProfile, decode_web_photo


router = APIRouter(tags=["Staff web profiles"])
_ADMIN = "/api/v1/admin/staff-web-profile"
_PREVIEW = f"{_ADMIN}/{{staff_id}}/preview"
_WEBSITE = f"{_ADMIN}/{{staff_id}}/website"
_LIFF = "/api/v1/line/staff-self-service/profile-change"
_CUSTOMER = "/api/v1/line/staff-web-profiles"
_REVIEW = "/api/v1/admin/staff-profile-change-requests"
_ID = Annotated[int, Path(gt=0)]
_IMAGE_FORMATS = {"JPEG": ("photo.jpg", "image/jpeg"), "PNG": ("photo.png", "image/png"),
                  "WEBP": ("photo.webp", "image/webp")}
_PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}


@router.get(f"{_ADMIN}/templates")
def list_templates(_=Depends(require_registry_writer)):
    with _translate_errors(), staff_web_profile_application() as web:
        return BaseResponse(data=web.repository.templates())


@router.post(f"{_ADMIN}/templates")
def add_template(body: TemplateItemInput, principal=Depends(require_registry_writer)):
    with _translate_errors(), staff_web_profile_application() as web:
        return BaseResponse(data=web.save_template(body.to_item(), admin_actor_context(principal)))


@router.put(f"{_ADMIN}/templates/{{item_id}}")
def edit_template(item_id: _ID, body: TemplateItemInput, principal=Depends(require_registry_writer)):
    with _translate_errors(), staff_web_profile_application() as web:
        return BaseResponse(data=web.save_template(body.to_item(item_id), admin_actor_context(principal)))


@router.get(f"{_ADMIN}/{{staff_id}}/folders", response_model=BaseResponse[FoldersView])
def staff_folders(staff_id: _ID, response: Response, _=Depends(require_registry_reader)):
    with _translate_errors(), staff_web_profile_application() as web:
        response.headers.update(_PRIVATE_HEADERS)
        items = tuple(FolderView.model_validate(folder) for folder in web.folders(staff_id))
        return BaseResponse(data=FoldersView(items=items))


@router.post(f"{_ADMIN}/{{staff_id}}/uploads", response_model=BaseResponse[UploadedPhotoView])
def upload_for_staff(
    staff_id: _ID, upload_id: Annotated[UUID, Form()], photograph: Annotated[UploadFile, File()],
    principal=Depends(require_registry_writer),
):
    with _translate_errors(), staff_web_profile_application() as web:
        filename, mime, data = _read_upload(photograph)
        filename = _uploaded_filename(photograph.filename, filename)
        uploaded = web.upload_for_staff(staff_id, upload_id, filename, mime, data, admin_actor_context(principal))
        return BaseResponse(data=UploadedPhotoView(file_id=uploaded.file_id, filename=uploaded.filename))


@router.post(f"{_ADMIN}/{{staff_id}}/publications", response_model=BaseResponse[PublicationsView])
def publish_for_staff(staff_id: _ID, body: PublicationInput, principal=Depends(require_registry_writer)):
    with _translate_errors(), staff_web_profile_application() as web:
        result = web.publish_uploaded(staff_id, body.to_photos(), body.operation_id, admin_actor_context(principal))
        return BaseResponse(data=PublicationsView(files=tuple(EntryVersionView.model_validate(file) for file in result)))


@router.delete(
    f"{_ADMIN}/{{staff_id}}/folders/{{template_item_id}}/entries/{{entry_id}}",
    response_model=BaseResponse[RemovedFileView],
)
def remove_staff_publication(
    staff_id: _ID, template_item_id: _ID, entry_id: _ID,
    template_version: Annotated[int, Query(gt=0)], entry_version: Annotated[int, Query(gt=0)],
    principal=Depends(require_registry_writer),
):
    with _translate_errors(), staff_web_profile_application() as web:
        web.remove_publication(
            staff_id, template_item_id, template_version, WebProfileEntryVersion(entry_id, entry_version),
            admin_actor_context(principal),
        )
        return BaseResponse(data=RemovedFileView(entry_id=entry_id))


@router.post(f"{_LIFF}/photos")
def upload_photo(
    upload_id: Annotated[UUID, Form()],
    photograph: Annotated[UploadFile, File()],
    line_id_token: Annotated[str, Form(max_length=4096)] = "",
    flow_id: Annotated[str, Form(max_length=191)] = "",
    development_line_user_id: Annotated[str, Form(max_length=191)] = "",
):
    staff_id = _bound_staff_id(StaffLiffRequest(
        line_id_token=line_id_token, flow_id=flow_id, development_line_user_id=development_line_user_id,
    ))
    with _translate_errors(), staff_profile_change_application() as (application, lifecycle):
        _require_active(lifecycle, staff_id)
        filename, mime, data = _read_upload(photograph)
        file_id = application.web_profile.upload_original(staff_id, upload_id, filename, mime, data)
        return BaseResponse(data={"file_id": file_id})


@router.get(f"{_REVIEW}/{{application_id}}/web-photos/{{photo_index}}")
def review_photo(
    application_id: _ID, photo_index: Annotated[int, Path(ge=0)],
    original: bool = False, _=Depends(require_registry_writer),
):
    with _translate_errors(), staff_web_profile_application() as web:
        item, photo = _review_photo(application_id, photo_index)
        contents = web.pending_image(item["staff_id"], photo, original=original)
        return _image_response(contents.content, contents.content_type)


@router.put(f"{_REVIEW}/{{application_id}}/web-photos/{{photo_index}}/crop")
def apply_crop(
    application_id: _ID, photo_index: Annotated[int, Path(ge=0)],
    body: CropInput, principal=Depends(require_registry_writer),
):
    with _translate_errors(), staff_web_profile_application() as web:
        item, photo = _review_photo(application_id, photo_index)
        _require_pending_version(item, body.version)
        contents = web.pending_image(item["staff_id"], photo, original=True)
        source, image_format = _decode_image(contents.content)
        left, top, right, bottom = body.box
        if not (left < right <= source.width and top < bottom <= source.height):
            raise ValueError("staff_web_crop_bounds_invalid")
        data = _encode_display_image(source.crop(body.box), image_format)
        if len(data) > file_transfer_settings().photo_max_bytes:
            raise ValueError("staff_web_photo_too_large")
        filename, mime = _IMAGE_FORMATS[image_format]
        file_id = web.save_crop(
            item["staff_id"], photo.original_file_id, body.crop_id, filename, mime, data,
            admin_actor_context(principal),
        )
        return BaseResponse(data=_update_photo_crop(item, photo_index, file_id))


@router.delete(f"{_REVIEW}/{{application_id}}/web-photos/{{photo_index}}/crop")
def discard_crop(
    application_id: _ID, photo_index: Annotated[int, Path(ge=0)],
    version: Annotated[int, Query(gt=0)], _=Depends(require_registry_writer),
):
    with _translate_errors():
        item, _ = _review_photo(application_id, photo_index)
        _require_pending_version(item, version)
        return BaseResponse(data=_update_photo_crop(item, photo_index, None))


@router.post(f"{_CUSTOMER}/{{staff_id}}/query")
def customer_profile(staff_id: _ID, body: CustomerWebProfileRequest):
    with _translate_errors(), staff_web_profile_application() as web:
        _require_customer_scope(staff_id, body)
        return BaseResponse(data=web.customer_page(staff_id))


@router.post(f"{_CUSTOMER}/{{staff_id}}/images/{{entry_id}}/{{version}}")
def customer_image(staff_id: _ID, entry_id: _ID, version: _ID, body: CustomerWebProfileRequest):
    with _translate_errors(), staff_web_profile_application() as web:
        _require_customer_scope(staff_id, body)
        return _published_image_response(web, staff_id, entry_id, version)


@router.get(_WEBSITE, response_model=BaseResponse[PublishedWebProfilePreviewView],
            dependencies=[Depends(require_registry_reader)])
@router.get(_PREVIEW, response_model=BaseResponse[PublishedWebProfilePreviewView],
            dependencies=[Depends(require_line_matching_reader)])
def preview_published_staff_web_profile(
    staff_id: _ID, response: Response,
):
    with _translate_errors(), staff_web_profile_application() as web:
        response.headers.update(_PRIVATE_HEADERS)
        return BaseResponse(data=web.customer_page(staff_id))


@router.get(f"{_WEBSITE}/images/{{entry_id}}/{{version}}", dependencies=[Depends(require_registry_reader)])
@router.get(f"{_PREVIEW}/images/{{entry_id}}/{{version}}", dependencies=[Depends(require_line_matching_reader)])
def preview_published_staff_web_image(
    staff_id: _ID, entry_id: _ID, version: _ID,
):
    with _translate_errors(), staff_web_profile_application() as web:
        return _published_image_response(web, staff_id, entry_id, version)


def _published_image_response(web: StaffWebProfile, staff_id: int, entry_id: int, version: int) -> Response:
    contents = web.customer_image(staff_id, entry_id, version)
    source, image_format = _decode_image(contents.content)
    return _image_response(_encode_display_image(source, image_format), _IMAGE_FORMATS[image_format][1])


def _require_customer_scope(staff_id: int, body: CustomerWebProfileRequest) -> None:
    identity = _verified_line_user_id(StaffLiffRequest(line_id_token=body.line_id_token))
    matching_notifications.require_customer_web_profile(body.interaction_token, identity, staff_id)


def _review_photo(application_id: int, index: int):
    item = staff_profile_change_staging().get(application_id)
    photos = item.get("content", {}).get("web_contents", ())
    if index >= len(photos):
        raise LookupError("staff_web_pending_photo_not_found")
    return item, decode_web_photo(photos[index])


def _require_pending_version(item, version: int):
    if item["status"] != "pending" or item["version"] != version:
        raise WebProfileConflict("staff_web_request_stale")


def _update_photo_crop(item, index: int, file_id: str | None):
    content, review = item["content"], item["review"]
    content["web_contents"][index]["crop_file_id"] = file_id
    review["web_contents"][index]["crop_file_id"] = file_id
    return _review(staff_profile_change_staging().update_web(item["id"], item["version"], content, review))


def _read_upload(photograph: UploadFile) -> tuple[str, str, bytes]:
    limit = file_transfer_settings().photo_max_bytes
    data = photograph.file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("staff_web_photo_too_large")
    if data[4:8] == b"ftyp":
        box_end = min(int.from_bytes(data[:4], "big"), len(data), 256)
        brands = {data[8:12], *(data[index:index + 4] for index in range(16, box_end, 4))}
        if brands & _HEIF_BRANDS:
            raise ValueError("staff_web_photo_heif_unsupported")
    _, image_format = _decode_image(data)
    filename, mime = _IMAGE_FORMATS[image_format]
    return filename, mime, data


def _uploaded_filename(original: str | None, detected: str) -> str:
    leaf = PureWindowsPath(original or "").name
    leaf = "".join(char for char in leaf if unicode_category(char) not in {"Cc", "Cf", "Cs"}).strip(" .")
    if not leaf:
        return detected
    path = PureWindowsPath(safe_filename_component(leaf))
    detected_suffix = PureWindowsPath(detected).suffix
    compatible = {".jpg", ".jpeg"} if detected_suffix == ".jpg" else {detected_suffix}
    suffix = path.suffix if path.suffix.lower() in compatible else detected_suffix
    stem = path.stem[:255 - len(suffix)].rstrip(" .")
    return f"{stem}{suffix}" if stem else detected


def _decode_image(data: bytes) -> tuple[Image.Image, str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=tuple(_IMAGE_FORMATS)) as image:
                image_format = image.format
                if getattr(image, "n_frames", 1) != 1 or image_format not in _IMAGE_FORMATS:
                    raise ValueError("staff_web_photo_format_invalid")
                image.load()
                return ImageOps.exif_transpose(image), image_format
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("staff_web_photo_format_invalid") from error


def _encode_display_image(source: Image.Image, image_format: str) -> bytes:
    alpha = "A" in source.getbands() or "transparency" in source.info
    image = source.convert("RGBA" if alpha and image_format != "JPEG" else "RGB")
    image.info.clear()
    stream = BytesIO()
    image.save(stream, image_format, quality=95)
    return stream.getvalue()


def _image_response(content: bytes, mime: str) -> Response:
    return Response(content, media_type=mime, headers=_PRIVATE_HEADERS)
