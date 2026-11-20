"""One authenticated media response implementation for Kitchen and Visual Menu."""
from pathlib import Path
from urllib.parse import urlsplit
import boto3
from botocore.exceptions import ClientError
from flask import Response,abort,current_app,send_file


def serve_kitchen_image(uri,mime=None):
    parsed=urlsplit(uri)
    if parsed.scheme=='s3':
        bucket=current_app.config.get('KITCHEN_MEDIA_BUCKET')
        key=parsed.path.lstrip('/')
        if not bucket or parsed.netloc!=bucket or not key.startswith('kitchen/'):abort(404)
        try:obj=boto3.client('s3').get_object(Bucket=bucket,Key=key)
        except ClientError as exc:
            abort(404 if exc.response.get('Error',{}).get('Code') in ('NoSuchKey','404') else 503)
        body=obj['Body']
        result=Response(body.iter_chunks(chunk_size=65536),mimetype=mime or obj.get('ContentType','application/octet-stream'))
        result.call_on_close(body.close)
    else:
        if current_app.config.get('KITCHEN_REQUIRE_S3'):abort(404)
        root=Path(__file__).resolve().parents[2];path=Path(uri).resolve()
        allowed=Path(current_app.config.get('KITCHEN_PLATING_UPLOAD_DIR',str(root/'output/kitchen-plating'))).resolve()
        if not (path.is_relative_to(root) or path.is_relative_to(allowed)) or path.suffix.lower() not in ('.jpg','.jpeg','.png','.webp') or not path.is_file():abort(404)
        result=send_file(path,mimetype=mime,conditional=False)
    result.headers['Cache-Control']='no-store';result.headers['X-Content-Type-Options']='nosniff'
    return result
