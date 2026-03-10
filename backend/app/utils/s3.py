from pathlib import Path
from uuid import uuid4

import boto3

from app.config import get_settings

settings = get_settings()


def save_upload_file(content: bytes, brand_id: str, upload_type: str, filename: str) -> str:
    key = f"{brand_id}/uploads/{upload_type}/{uuid4()}/{filename}"
    if settings.local_storage:
        path = Path(settings.local_storage_path) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    s3.put_object(Bucket=settings.s3_bucket_name, Key=key, Body=content)
    return key


def read_upload_file(path_or_key: str) -> bytes:
    if settings.local_storage:
        return Path(path_or_key).read_bytes()

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    obj = s3.get_object(Bucket=settings.s3_bucket_name, Key=path_or_key)
    return obj["Body"].read()
