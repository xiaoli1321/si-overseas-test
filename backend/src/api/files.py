from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.exceptions import NotFoundError
from src.core.responses import ok
from src.models.tables import User
from src.repositories.files import get_uploaded_file
from src.schemas.domain import UploadedFileResponse
from src.services.audit import record_audit_event
from src.services.files import save_uploaded_file
from src.services.storage import get_stored_file_download_url, stored_file_exists

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> dict:
    db_file = await save_uploaded_file(db, user.id, file)
    await record_audit_event(
        db,
        user_id=user.id,
        action="file.upload",
        target_type="uploaded_file",
        target_id=db_file.id,
        metadata={
            "filename": db_file.filename,
            "mime_type": db_file.mime_type,
            "file_size": db_file.file_size,
        },
    )
    await db.commit()
    return ok(UploadedFileResponse.model_validate(db_file).model_dump())


@router.get("/{file_id}")
async def download_endpoint(
    file_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    db_file = await get_uploaded_file(db, user.id, file_id)
    if db_file is None:
        raise NotFoundError("Uploaded file was not found.")

    download_url = await get_stored_file_download_url(db_file)
    if download_url:
        return RedirectResponse(download_url)

    if not await stored_file_exists(db_file):
        raise NotFoundError("Physical file was not found on disk.")

    return FileResponse(
        path=db_file.object_key,
        filename=db_file.filename,
        media_type=db_file.mime_type,
    )
