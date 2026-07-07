from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import UploadedFile
from src.repositories.files import create_uploaded_file
from src.services.storage import new_file_id, save_bytes_to_storage


async def save_uploaded_file(
    db: AsyncSession, user_id: int, file: UploadFile
) -> UploadedFile:
    file_id = new_file_id()
    filename = file.filename or "unknown"
    contents = await file.read()
    stored = await save_bytes_to_storage(
        user_id=user_id,
        file_id=file_id,
        filename=filename,
        data=contents,
        content_type=file.content_type,
    )

    db_file = await create_uploaded_file(
        db,
        file_id=file_id,
        user_id=user_id,
        filename=filename,
        storage_backend=stored.storage_backend,
        object_key=stored.object_key,
        file_size=stored.file_size,
    )

    await db.flush()
    await db.refresh(db_file)
    return db_file
