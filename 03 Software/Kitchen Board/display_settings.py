"""Validated, versioned display preferences; no source-order data is modified."""
from sqlalchemy import ForeignKey, Integer, JSON, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.exc import IntegrityError
from rfone_data_store import models as m

DEFAULTS={'font_family':'arial','font_size':20,'row_count':1,'layout':'flow'}
FONT_FAMILIES={'arial':'Arial','segoe':'Segoe UI','verdana':'Verdana'}
LAYOUTS=('flow','cards')


class DisplaySettings(m.Base):
    __tablename__='kitchen_display_settings'
    location_id: Mapped[int]=mapped_column(ForeignKey('kitchen_boards.location_id'),primary_key=True)
    values: Mapped[dict]=mapped_column(JSON,nullable=False)
    revision: Mapped[int]=mapped_column(Integer,nullable=False,default=1)


class SettingsError(ValueError): pass
class SettingsConflict(SettingsError): pass


def read_settings(db,board):
    row=db.get(DisplaySettings,board.location_id)
    return {**DEFAULTS,**(row.values if row else {}),'visible_count':board.visible_count,
            'revision':row.revision if row else 0}


def validated(values, *, form=False):
    if not isinstance(values,dict): raise SettingsError('invalid')
    result={}
    limits={'visible_count':(1,16),'font_size':(12,36),'row_count':(1,3)}
    for key,(low,high) in limits.items():
        if key not in values: continue
        value=values[key]
        if form:
            if not isinstance(value,str) or not value.isascii() or not value.isdigit(): raise SettingsError(key)
            value=int(value)
        if type(value) is not int or not low<=value<=high: raise SettingsError(key)
        result[key]=value
    for key,allowed in [('font_family',FONT_FAMILIES),('layout',LAYOUTS)]:
        if key in values:
            if not isinstance(values[key],str) or values[key] not in allowed: raise SettingsError(key)
            result[key]=values[key]
    if not result: raise SettingsError('invalid')
    return result


def save_settings(db,board,changes,expected_revision=None):
    current=read_settings(db,board)
    if expected_revision is not None and expected_revision!=current['revision']:
        raise SettingsConflict('conflict')
    merged={**current,**changes}; revision=current['revision']
    stored={key:merged[key] for key in DEFAULTS}
    if revision:
        affected=db.execute(update(DisplaySettings).where(
            DisplaySettings.location_id==board.location_id,DisplaySettings.revision==revision
        ).values(values=stored,revision=revision+1)).rowcount
        if not affected: raise SettingsConflict('conflict')
    else:
        db.add(DisplaySettings(location_id=board.location_id,values=stored,revision=1))
        try: db.flush()
        except IntegrityError as exc:
            db.rollback(); raise SettingsConflict('conflict') from exc
    board.visible_count=merged['visible_count']
    db.commit()
    return {**merged,'revision':revision+1}
