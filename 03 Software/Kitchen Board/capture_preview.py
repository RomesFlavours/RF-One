"""Read-only real Clover ticket capture for visual review; never modifies Clover/DB."""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bootstrap  # noqa: F401
from clover_explorer.client import CloverClient
from clover_explorer.config import CloverConfig, _parse_dotenv
from clover_explorer.pagination import paginate
from rfone_data_store.technical.connectors.clover.source_guard import require_complete, require_ok
from sync import ticket_payload
from kitchen_filter import kitchen_payload


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dotenv', required=True)
    parser.add_argument('--output', required=True)
    args=parser.parse_args()
    env=_parse_dotenv(Path(args.dotenv))
    client=CloverClient(CloverConfig(merchant_id=os.environ.get('CLOVER_MERCHANT_ID') or env['CLOVER_MERCHANT_ID'],
                                   api_token=os.environ.get('CLOVER_API_TOKEN') or env['CLOVER_API_TOKEN']))
    mid=client.merchant_id
    merchant=require_ok(client.get(f'/v3/merchants/{mid}'),'Merchant')
    groups=require_complete(paginate(client,f'/v3/merchants/{mid}/modifier_groups',extra_params={'expand':'modifiers'}),'Modifier groups')
    timings={mod['id']:mod['name'] for group in groups if group.get('name','').casefold()=='when serve'
             for mod in group.get('modifiers',{}).get('elements',[])}
    items=require_complete(paginate(client,f'/v3/merchants/{mid}/items',extra_params={'expand':'categories'}),'Item categories')
    categories={item['id']:[cat.get('name','') for cat in item.get('categories',{}).get('elements',[])] for item in items}
    current=datetime.now(timezone.utc)
    start=current-timedelta(days=2)
    orders=require_complete(paginate(client,f'/v3/merchants/{mid}/orders',extra_params={
        'filter':[f'createdTime>={int(start.timestamp()*1000)}',f'createdTime<={int(current.timestamp()*1000)}']}),'Recent orders')
    tickets=[]
    for raw in sorted(orders,key=lambda row:row.get('createdTime',0),reverse=True):
        lines=require_complete(paginate(client,f'/v3/merchants/{mid}/orders/{raw["id"]}/line_items',extra_params={'expand':'modifications'}),'Order items')
        payload=ticket_payload(raw,lines)
        source={line.get('id'):line for line in lines}
        for line in payload['lines']:
            original=source[line['id']]
            line['categories']=categories.get((original.get('item') or {}).get('id'),[])
            line['service_timing']=list(dict.fromkeys(timings[mod.get('modifier',{}).get('id')]
                for mod in original.get('modifications',{}).get('elements',[])
                if mod.get('modifier',{}).get('id') in timings))
        payload=kitchen_payload(payload,{})
        if not payload['lines']: continue
        created=datetime.fromtimestamp(raw['createdTime']/1000,timezone.utc)
        from zoneinfo import ZoneInfo
        tickets.append({**payload,'order_id':raw['id'],'created_at':created.isoformat(),
            'local_time':created.astimezone(ZoneInfo('America/New_York')).strftime('%H:%M'),
            'rfone_order_id':None,'released_at':None,'released_by':None})
        if len(tickets)==6: break
    tickets.sort(key=lambda row:row['created_at'])
    output={'orders':tickets,'visible_count':6,'total':len(tickets),'last_sync':current.isoformat(),
        'sync_error':False,'stale':False,'preview_source':'Clover online',
        'merchant_name':merchant.get('name'),'captured_at':current.isoformat()}
    Path(args.output).write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'orders':len(tickets),'items':sum(len(t['lines']) for t in tickets),
        'with_service_timing':sum(bool(line['service_timing']) for t in tickets for line in t['lines']),
        'when_serve_values':list(timings.values()),'captured_at':current.isoformat()}))


if __name__=='__main__': main()
