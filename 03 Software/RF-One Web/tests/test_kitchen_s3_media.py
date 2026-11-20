"""Private S3 persistence/streaming contract without any AWS calls."""
from io import BytesIO
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_kitchen_recipe_editor import build_app


class Body(BytesIO):
    def iter_chunks(self,chunk_size):
        while True:
            data=self.read(chunk_size)
            if not data:return
            yield data


class Storage:
    def __init__(self):self.objects={}
    def put_object(self,**kw):
        assert kw['ServerSideEncryption']=='AES256'
        self.objects[(kw['Bucket'],kw['Key'])]=(kw['Body'],kw['ContentType'])
    def get_object(self,**kw):
        data,mime=self.objects[(kw['Bucket'],kw['Key'])];return dict(Body=Body(data),ContentType=mime)
    def delete_object(self,**kw):self.objects.pop((kw['Bucket'],kw['Key']),None)


def main():
    app,engine=build_app();app.config.update(KITCHEN_MEDIA_BUCKET='private-test',KITCHEN_REQUIRE_S3=True)
    c=app.test_client();rid=c.post('/kitchen/recipes/save',data=dict(csrf_token='test-csrf',name='S3 test',kind='dish',draft_key=str(uuid4()))).json['recipe']['id']
    stream=BytesIO();Image.new('RGB',(2,2),'green').save(stream,format='PNG');data=stream.getvalue();storage=Storage()
    with patch('rfone_data_store.kitchen_plating.boto3.client',return_value=storage):
        path=f'/kitchen/recipes/{rid}/plating'
        result=c.post(path,data=dict(csrf_token='test-csrf',revision=1,description='Standard plating',image=(BytesIO(data),'image.png')),content_type='multipart/form-data')
        assert result.status_code==200,result.text
        assert len(storage.objects)==1
        picture=c.get(c.get(path).json['image_url']);assert picture.status_code==200 and picture.data==data and picture.mimetype=='image/png';picture.close()
        assert c.post(path,data=dict(csrf_token='test-csrf',revision=1,description='Stale',image=(BytesIO(data),'image.png')),content_type='multipart/form-data').status_code==409
        assert len(storage.objects)==1
    engine.dispose();print('PASS: encrypted private S3 upload, authenticated exact-byte streaming, stale save rejected before upload, no live AWS calls')


if __name__=='__main__':main()
