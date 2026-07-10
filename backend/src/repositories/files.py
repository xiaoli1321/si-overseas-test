from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.utils import string_to_bigint
from src.models.tables import UploadedFile
from src.repositories.scopes import apply_user_scope


async def create_uploaded_file(
    db: AsyncSession,
    *,
    file_id: str,
    user_id: int,
    filename: str,
    storage_backend: str,
    object_key: str,
    file_size: int,
) -> UploadedFile:
    db_file = UploadedFile(
        id=string_to_bigint(file_id),
        user_id=user_id,
        filename=filename,
        storage_backend=storage_backend,
        object_key=object_key,
        file_size=file_size,
    )
    db.add(db_file)
    await db.flush()
    return db_file


async def get_uploaded_file(
    db: AsyncSession, user_id: int, file_id: str
) -> UploadedFile | None:
    query = apply_user_scope(select(UploadedFile), UploadedFile, user_id).where(
        UploadedFile.id == string_to_bigint(file_id)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_uploaded_files(
    db: AsyncSession,
    user_id: int,
    file_ids: list[str],
) -> Sequence[UploadedFile]:
    if not file_ids:
        return []
    mapped_ids = [string_to_bigint(fid) for fid in file_ids]
    query = apply_user_scope(select(UploadedFile), UploadedFile, user_id).where(
        UploadedFile.id.in_(mapped_ids)
    )
    result = await db.execute(query)
    return result.scalars().all()


async def bind_uploaded_files_to_record(
    db: AsyncSession,
    *,
    user_id: int,
    file_ids: list[str],
    detect_record_id: int,
) -> None:
    """Bind partner-uploaded evidence once; a file cannot back multiple API tasks."""
    if not file_ids:
        return
    mapped_ids = [string_to_bigint(file_id) for file_id in file_ids]
    result = await db.execute(
        update(UploadedFile)
        .where(
            UploadedFile.user_id == user_id,
            UploadedFile.id.in_(mapped_ids),
            UploadedFile.detect_record_id.is_(None),
        )
        .values(detect_record_id=detect_record_id)
    )
    if result.rowcount != len(set(mapped_ids)):
        raise ValueError("One or more files are already bound to another detection.")
