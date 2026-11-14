"""本地演练：领取期间来源更新一次共享模板。

演练流程：先在模板修订 20 下领取页面 1、5、6；来源推进一次
（Template:Capacity 20→21，正文修订不变）；再领取页面 2、3、4、5、6。
随后增量扫描找出受共享模板更新影响的页面并重新领取，最后复查与出报告。
"""

from pathlib import Path
import tempfile

from .archive import archive_file
from .client import SourceClient
from .collect import collect_pages, report, scan_dependencies
from .core import inspect_file
from .http_source import source_server
from .store import Store

SAMPLE = 'fixtures/page.json'


def run_demo():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        store = Store(directory / 'store')
        with source_server('fixtures') as (address, state):
            client = SourceClient(address)
            before = collect_pages(client, store, [1, 5, 6])
            advance = client.post_json('/control/advance')
            after = collect_pages(client, store, [2, 3, 4, 5, 6])
            scan = scan_dependencies(client, store)
            recollect = collect_pages(client, store, scan['stale_pages'])
            rescan = scan_dependencies(client, store)
            final = report(store)
        return {
            '原始资料': archive_file(Path(SAMPLE), directory / 'raw'),
            '资料预览': inspect_file(Path(SAMPLE)),
            '采集演练': {
                '说明': '领取期间来源推进一次共享模板修订（Template:Capacity 20→21），正文修订不变',
                '模板更新前领取': before,
                '来源推进': advance,
                '模板更新后领取': after,
                '增量扫描': scan,
                '受影响页面': scan['stale_pages'],
                '受影响页面重新领取': recollect,
                '复查': rescan,
                '无法证明新鲜度的页面': [entry['pageid'] for entry in rescan['unverifiable']
                                     if 'pageid' in entry],
                '最终报告': final,
            },
        }
