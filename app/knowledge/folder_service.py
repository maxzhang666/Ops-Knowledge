import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.knowledge.models import Folder
from app.knowledge.schemas import FolderCreate, FolderTreeResponse, FolderUpdate


class FolderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_folder(self, kb_id: uuid.UUID, data: FolderCreate) -> Folder:
        if data.parent_folder_id:
            parent = await self.db.get(Folder, data.parent_folder_id)
            if parent is None or parent.knowledge_base_id != kb_id:
                raise ValidationError("Parent folder not found in this knowledge base")

        folder = Folder(
            knowledge_base_id=kb_id,
            name=data.name,
            parent_folder_id=data.parent_folder_id,
            position=data.position,
        )
        self.db.add(folder)
        await self.db.flush()
        return folder

    async def get_folder(self, folder_id: uuid.UUID) -> Folder:
        folder = await self.db.get(Folder, folder_id)
        if folder is None:
            raise NotFoundError("Folder", str(folder_id))
        return folder

    async def update_folder(self, folder_id: uuid.UUID, data: FolderUpdate) -> Folder:
        folder = await self.get_folder(folder_id)
        updates = data.model_dump(exclude_unset=True)
        for k, v in updates.items():
            setattr(folder, k, v)
        await self.db.flush()
        return folder

    async def delete_folder(self, folder_id: uuid.UUID) -> None:
        folder = await self.get_folder(folder_id)
        await self.db.delete(folder)
        await self.db.flush()

    async def get_folder_tree(self, kb_id: uuid.UUID) -> list[FolderTreeResponse]:
        result = await self.db.scalars(
            select(Folder)
            .where(Folder.knowledge_base_id == kb_id)
            .order_by(Folder.position, Folder.name)
        )
        all_folders = result.all()

        folder_map: dict[uuid.UUID, FolderTreeResponse] = {}
        for f in all_folders:
            folder_map[f.id] = FolderTreeResponse.model_validate(f)

        roots: list[FolderTreeResponse] = []
        for fr in folder_map.values():
            if fr.parent_folder_id and fr.parent_folder_id in folder_map:
                folder_map[fr.parent_folder_id].children.append(fr)
            else:
                roots.append(fr)
        return roots
