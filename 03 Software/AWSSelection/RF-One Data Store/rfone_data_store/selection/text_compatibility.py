"""PostgreSQL-safe text at the ingestion boundary; original document bytes stay unchanged."""
def postgres_text(value):
    if isinstance(value,str):return value.replace('\x00','')
    if isinstance(value,list):return [postgres_text(v) for v in value]
    if isinstance(value,tuple):return tuple(postgres_text(v) for v in value)
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            cleaned=postgres_text(key)
            if cleaned in result:raise ValueError('Text normalization would create duplicate JSON keys.')
            result[cleaned]=postgres_text(item)
        return result
    return value
