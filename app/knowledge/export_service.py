import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import Chunk, Document, Folder, KnowledgeBase
from app.knowledge.storage.minio_service import MinIOService

logger = structlog.get_logger(__name__)

OKA_VERSION = "1.0"


class ExportService:
    def __init__(self, db: AsyncSession, minio: MinIOService | None = None):
        self.db = db
        self.minio = minio or MinIOService()

    async def export_kb(self, kb_id: uuid.UUID) -> bytes:
        kb = await self.db.get(KnowledgeBase, kb_id)
        if kb is None:
            raise ValueError("Knowledge base not found")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            manifest = {
                "oka_version": OKA_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "kb_id": str(kb.id),
                "kb_name": kb.name,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            config = {
                "name": kb.name,
                "description": kb.description,
                "embedding_model_name": kb.embedding_model_name,
                "chunking_config": kb.chunking_config,
                "retrieval_config": kb.retrieval_config,
            }
            zf.writestr("config.json", json.dumps(config, indent=2))

            folders = (await self.db.execute(
                select(Folder).where(Folder.knowledge_base_id == kb_id)
            )).scalars().all()
            folders_data = [
                {"id": str(f.id), "name": f.name, "parent_folder_id": str(f.parent_folder_id) if f.parent_folder_id else None, "position": f.position}
                for f in folders
            ]
            zf.writestr("folders.json", json.dumps(folders_data, indent=2))

            docs = (await self.db.execute(
                select(Document).where(Document.knowledge_base_id == kb_id, Document.is_archived.is_(False))
            )).scalars().all()

            for doc in docs:
                doc_meta = {
                    "id": str(doc.id),
                    "title": doc.title,
                    "source_type": doc.source_type,
                    "folder_id": str(doc.folder_id) if doc.folder_id else None,
                    "file_size": doc.file_size,
                    "file_hash": doc.file_hash,
                    "chunk_count": doc.chunk_count,
                    "token_count": doc.token_count,
                }
                zf.writestr(f"documents/{doc.id}/meta.json", json.dumps(doc_meta, indent=2))

                try:
                    file_data = await self.minio.download(doc.file_path)
                    zf.writestr(f"documents/{doc.id}/{doc.title}", file_data)
                except Exception:
                    logger.warning("export_file_download_failed", doc_id=str(doc.id))

            chunks = (await self.db.execute(
                select(Chunk).where(Chunk.knowledge_base_id == kb_id)
            )).scalars().all()

            lines = []
            for c in chunks:
                lines.append(json.dumps({
                    "id": str(c.id),
                    "document_id": str(c.document_id),
                    "content": c.content,
                    "level": c.level,
                    "position": c.position,
                    "token_count": c.token_count,
                    "metadata": c.metadata_,
                }))
            zf.writestr("chunks.jsonl", "\n".join(lines))

        logger.info("kb_exported", kb_id=str(kb_id), doc_count=len(docs))
        return buf.getvalue()

    async def import_kb(
        self,
        archive_data: bytes,
        user_id: uuid.UUID,
        re_chunk: bool = False,
    ) -> uuid.UUID:
        buf = io.BytesIO(archive_data)
        with zipfile.ZipFile(buf, "r") as zf:
            config = json.loads(zf.read("config.json"))

            kb = KnowledgeBase(
                name=config["name"],
                description=config.get("description"),
                embedding_model_name=config.get("embedding_model_name"),
                chunking_config=config.get("chunking_config"),
                retrieval_config=config.get("retrieval_config"),
                created_by=user_id,
            )
            self.db.add(kb)
            await self.db.flush()

            folder_id_map: dict[str, uuid.UUID] = {}
            if "folders.json" in zf.namelist():
                folders_data = json.loads(zf.read("folders.json"))
                for fd in folders_data:
                    new_folder = Folder(
                        knowledge_base_id=kb.id,
                        name=fd["name"],
                        position=fd.get("position", 0),
                    )
                    self.db.add(new_folder)
                    await self.db.flush()
                    folder_id_map[fd["id"]] = new_folder.id

                for fd in folders_data:
                    if fd.get("parent_folder_id") and fd["parent_folder_id"] in folder_id_map:
                        new_id = folder_id_map[fd["id"]]
                        parent_id = folder_id_map[fd["parent_folder_id"]]
                        folder_obj = await self.db.get(Folder, new_id)
                        if folder_obj:
                            folder_obj.parent_folder_id = parent_id
                await self.db.flush()

            doc_dirs = {n.split("/")[1] for n in zf.namelist() if n.startswith("documents/") and n.count("/") >= 2}
            doc_id_map: dict[str, uuid.UUID] = {}

            for doc_dir in doc_dirs:
                meta_path = f"documents/{doc_dir}/meta.json"
                if meta_path not in zf.namelist():
                    continue
                meta = json.loads(zf.read(meta_path))

                mapped_folder = folder_id_map.get(meta.get("folder_id")) if meta.get("folder_id") else None

                doc = Document(
                    knowledge_base_id=kb.id,
                    folder_id=mapped_folder,
                    title=meta["title"],
                    source_type=meta["source_type"],
                    file_path="",
                    file_size=meta.get("file_size", 0),
                    file_hash=meta.get("file_hash", ""),
                    chunk_count=meta.get("chunk_count", 0),
                    token_count=meta.get("token_count", 0),
                    created_by=user_id,
                )
                self.db.add(doc)
                await self.db.flush()
                doc_id_map[meta["id"]] = doc.id

                file_path_in_zip = f"documents/{doc_dir}/{meta['title']}"
                if file_path_in_zip in zf.namelist():
                    file_data = zf.read(file_path_in_zip)
                    key = f"kb/{kb.id}/{doc.id}/{meta['title']}"
                    await self.minio.upload(key, file_data)
                    doc.file_path = key
                    await self.db.flush()

            if not re_chunk and "chunks.jsonl" in zf.namelist():
                chunk_data = zf.read("chunks.jsonl").decode("utf-8")
                for line in chunk_data.strip().split("\n"):
                    if not line.strip():
                        continue
                    cd = json.loads(line)
                    new_doc_id = doc_id_map.get(cd["document_id"])
                    if new_doc_id is None:
                        continue
                    chunk = Chunk(
                        document_id=new_doc_id,
                        knowledge_base_id=kb.id,
                        content=cd["content"],
                        level=cd.get("level", 0),
                        position=cd.get("position", 0),
                        token_count=cd.get("token_count", 0),
                        metadata_=cd.get("metadata"),
                    )
                    self.db.add(chunk)
                await self.db.flush()

            kb.document_count = len(doc_id_map)
            await self.db.flush()

        logger.info("kb_imported", kb_id=str(kb.id), doc_count=len(doc_id_map))
        return kb.id
