import json
from pathlib import Path


def inspect_file(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    return {'pageid':value['pageid'],'title':value['title'],'revision':value['revid'],'source_text':value['text']}
