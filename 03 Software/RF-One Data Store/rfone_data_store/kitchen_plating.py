"""Plating description and image storage using existing Kitchen recipe/photo tables."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit
import boto3
from PIL import Image, UnidentifiedImageError
import sqlalchemy as sa
from .kitchen import recipes,photos,menu_links
from .kitchen_editor import EditorError,StaleRecipe,integer,record,summary

UPLOAD_SOURCE='Kitchen plating upload'
LIMIT=10*1024*1024
FORMATS={'JPEG':('jpg','image/jpeg'),'PNG':('png','image/png'),'WEBP':('webp','image/webp')}


@dataclass
class StoredAsset:
    uri: str

    def unlink(self,missing_ok=True):
        parsed=urlsplit(self.uri)
        if parsed.scheme=='s3':boto3.client('s3').delete_object(Bucket=parsed.netloc,Key=parsed.path.lstrip('/'))
        else:Path(self.uri).unlink(missing_ok=missing_ok)


def current_photo(db,rid):
    return db.execute(sa.select(photos).where(photos.c.recipe_id==rid)
        .order_by((photos.c.source==UPLOAD_SOURCE).desc().nulls_last(),photos.c.id.desc()).limit(1)).mappings().first()


def read(db,rid):
    r=record(db,rid)
    return dict(recipe=summary(db,rid),description=r['plating_instructions'] or '',photo=current_photo(db,rid))


def validate_image(content):
    if not content or len(content)>LIMIT:raise EditorError('Choose an image up to 10 MB.')
    try:
        with Image.open(BytesIO(content)) as image:
            kind=image.format
            if kind not in FORMATS or image.width*image.height>40000000:raise EditorError('Choose a JPEG, PNG or WebP image up to 40 megapixels.')
            image.verify()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as exc:
        if isinstance(exc,EditorError):raise
        raise EditorError('The file is not a valid JPEG, PNG or WebP image.') from exc
    return FORMATS[kind]


def save(db,rid,*,revision,description,content=None,directory,storage_bucket=None):
    r=record(db,rid,True)
    if integer(revision)!=r['revision']:raise StaleRecipe('This recipe changed after you opened it. Close and reopen Plating before saving.')
    description=description or ''
    if len(description)>20000:raise EditorError('Plating description must be at most 20,000 characters.')
    path=None
    try:
        if content is not None:
            extension,mime=validate_image(content)
            filename=uuid4().hex+'.'+extension
            if storage_bucket:
                object_key='kitchen/plating/'+filename
                boto3.client('s3').put_object(Bucket=storage_bucket,Key=object_key,Body=content,ContentType=mime,ServerSideEncryption='AES256')
                path=StoredAsset('s3://'+storage_bucket+'/'+object_key)
            else:
                directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
                target=directory/filename
                with target.open('xb') as output:output.write(content)
                path=StoredAsset(str(target.resolve()))
            pid=db.execute(photos.insert().values(recipe_id=rid,asset_uri=path.uri,
                sha256=hashlib.sha256(content).hexdigest(),mime_type=mime,
                caption=r['name']+' — standard plating',alt_text=r['name']+' — plating image',source=UPLOAD_SOURCE)
                .returning(photos.c.id)).scalar_one()
            db.execute(menu_links.update().where(menu_links.c.recipe_id==rid).values(standard_photo_id=pid))
        db.execute(recipes.update().where(recipes.c.id==rid).values(plating_instructions=description or None,
            revision=r['revision']+1,validation_status='pending',validated_at=None,validated_by_id=None))
        return summary(db,rid),path
    except Exception:
        if path:path.unlink(missing_ok=True)
        raise
