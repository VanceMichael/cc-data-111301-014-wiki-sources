"""快照仓库：pages/ 每页一条记录，raw/ 保存原始响应字节。

每页记录保存当前可用快照、历史快照、领取尝试（含失败）、重定向别名与
增量扫描的过期标记。依赖反查索引由快照即时推导，不另存副本，避免两处
依据不一致。
"""

import json
import os
from pathlib import Path
import tempfile

from .archive import archive_bytes


class Store:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / 'pages').mkdir(parents=True, exist_ok=True)
        (self.root / 'raw').mkdir(parents=True, exist_ok=True)

    def archive(self, data):
        return archive_bytes(data, self.root / 'raw')['sha256']

    def _path(self, pageid):
        return self.root / 'pages' / f'{pageid}.json'

    def load_page(self, pageid):
        path = self._path(pageid)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))

    def save_page(self, record):
        path = self._path(record['pageid'])
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w',
                                             encoding='utf-8') as writer:
                temporary = Path(writer.name)
                writer.write(json.dumps(record, ensure_ascii=False, indent=2))
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def page_ids(self):
        return sorted(int(path.stem) for path in (self.root / 'pages').glob('*.json'))

    def all_pages(self):
        return [self.load_page(pageid) for pageid in self.page_ids()]

    def dependency_index(self):
        """已证明依赖的反查索引：{依赖标题: {pageid: 记录的修订}}。"""
        index = {}
        for record in self.all_pages():
            current = record.get('current')
            if not current:
                continue
            for dependency in current['dependencies']:
                if dependency['status'] == 'proven':
                    index.setdefault(dependency['title'], {})[record['pageid']] = dependency['revid']
        return index


def new_record(pageid, title):
    return {'pageid': pageid, 'title': title, 'aliases': [], 'current': None,
            'history': [], 'attempts': [], 'stale': False, 'stale_reasons': [],
            'last_change': None}
