"""Plating upload/description lifecycle using disposable memory and a temp directory."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import hashlib
import sys
from PIL import Image
import sqlalchemy as sa
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_kitchen_recipe_editor import build_app
from rfone_data_store.kitchen import recipes,photos,menu_cards,menu_links


def png(color):
    stream=BytesIO();Image.new('RGB',(4,4),color).save(stream,format='PNG');return stream.getvalue()


def main():
    app,engine=build_app();c=app.test_client()
    with TemporaryDirectory(prefix='kitchen-plating-test-') as directory:
        app.config['KITCHEN_PLATING_UPLOAD_DIR']=directory
        rid=c.post('/kitchen/recipes/save',data=dict(csrf_token='test-csrf',name='Plating test',kind='dish',draft_key=str(uuid4()))).json['recipe']['id']
        with engine.begin() as db:
            db.exec_driver_sql('INSERT INTO restaurants(id) VALUES(1)')
            db.execute(menu_cards.insert().values(restaurant_id=1,dish_key='test',title='Test',content_version=1,validation_status='pending',content_json='{}'))
            db.execute(menu_links.insert().values(restaurant_id=1,dish_key='test',recipe_id=rid))
        path=f'/kitchen/recipes/{rid}/plating'
        assert c.get(path).json['image_url'] is None
        assert c.get(path).json['recipe']['has_photo'] is False
        def save(revision,description,image=None):
            data=dict(csrf_token='test-csrf',revision=str(revision),description=description)
            if image is not None:data['image']=(BytesIO(image),'photo.png')
            return c.post(path,data=data,content_type='multipart/form-data')
        assert save(1,'Initial description').status_code==200
        bad=save(2,'Must not save',b'<svg>not an allowed bitmap</svg>')
        assert bad.status_code==400 and c.get(path).json['description']=='Initial description'
        assert not list(Path(directory).iterdir())
        image=png('green');saved=save(2,'Plate in the centre',image)
        assert saved.status_code==200,saved.text
        assert saved.json['recipe']['has_photo'] is True
        page=c.get('/kitchen/recipes').text
        row=page.split(f'data-recipe-id="{rid}"',1)[1].split('</tr>',1)[0]
        assert 'recipe-action-buttons' in row and 'data-photo-check' in row
        assert 'title="Plating photo available" hidden' not in row
        result=c.get(path).json;first_url=result['image_url'];served=c.get(first_url)
        assert served.status_code==200 and served.data==image and served.mimetype=='image/png'
        assert served.headers['Cache-Control']=='no-store'
        served.close()
        with engine.connect() as db:
            photo=db.execute(sa.select(photos)).mappings().one()
            assert photo['sha256']==hashlib.sha256(image).hexdigest()
            assert db.scalar(sa.select(menu_links.c.standard_photo_id))==photo['id']
        assert save(3,'Description only').status_code==200
        assert c.get(path).json['image_url']==first_url
        assert save(3,'Stale',png('red')).status_code==409
        assert len(list(Path(directory).iterdir()))==1
        assert save(4,'Updated image',png('blue')).status_code==200
        assert c.get(path).json['image_url']!=first_url
        assert len(list(Path(directory).iterdir()))==2
        assert c.post(path,data=dict(revision=5,description='No CSRF')).status_code==400
        from rfone_data_store.kitchen_plating import current_photo,UPLOAD_SOURCE
        with engine.begin() as db:
            left=db.execute(photos.insert().values(recipe_id=rid,asset_uri=str(Path(directory)/'left.png'),source=UPLOAD_SOURCE).returning(photos.c.id)).scalar_one()
            right=db.execute(photos.insert().values(recipe_id=rid,asset_uri=str(Path(directory)/'right.png'),source='Kitchen menu topping variant').returning(photos.c.id)).scalar_one()
            assert right>left and current_photo(db,rid)['id']==left
        with engine.begin() as db:
            db.exec_driver_sql("UPDATE rfone_account_domain_access SET scope='SELECTED'")
            db.exec_driver_sql("INSERT INTO rfone_account_domain_item_access VALUES (1,'KITCHEN','DASHBOARD')")
        assert c.get(path).status_code==403 and c.get(path+'/image').status_code==403
        assert save(5,'Forbidden').status_code==403
        assert len(list(Path(directory).iterdir()))==2
    engine.dispose()
    print('PASS: description-only, validated image upload/preview endpoint, exact bytes/MIME/hash, Menu link, replacement/history, stale rejection, CSRF and permissions')


if __name__=='__main__':main()
