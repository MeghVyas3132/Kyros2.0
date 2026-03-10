import asyncio
import json
import sys
from uuid import UUID

from app.database import AsyncSessionLocal
from app.models import Upload
from app.services.ingestion.processor import process_upload


async def run_upload(upload_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        upload = await db.get(Upload, UUID(upload_id))
        if upload is None:
            raise ValueError(f"Upload {upload_id} not found")

        await process_upload(db, upload)
        await db.commit()
        return {
            "upload_id": str(upload.id),
            "status": upload.status.value,
            "successful_rows": upload.successful_rows,
            "failed_rows": upload.failed_rows,
        }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.tasks.upload_runner <upload_id>")
    result = asyncio.run(run_upload(sys.argv[1]))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
