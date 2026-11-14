from pathlib import Path
import tempfile
import unittest

from wiki_sources.client import SourceClient
from wiki_sources.collect import (collect_pages, consistency_of, content_key,
                                  normalize_dependency, report,
                                  scan_dependencies)
from wiki_sources.http_source import source_server
from wiki_sources.store import Store


class CollectFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Store(Path(self.temporary.name) / 'store')
        self.server = source_server('fixtures')
        address, self.state = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        self.client = SourceClient(address)

    def advance(self):
        self.client.post_json('/control/advance')

    def test_template_change_marks_only_dependent_pages_stale(self):
        collect_pages(self.client, self.store, [1, 5, 6])
        self.advance()
        collect_pages(self.client, self.store, [2])
        scan = scan_dependencies(self.client, self.store)
        # 只有记录了 Capacity@20 的页面 1 需要重新领取，不是全站重抓
        self.assertEqual(scan['stale_pages'], [1])
        collect_pages(self.client, self.store, scan['stale_pages'])
        again = scan_dependencies(self.client, self.store)
        self.assertEqual(again['stale_pages'], [])
        record = self.store.load_page(1)
        # 正文修订没变，是依赖变化导致内容版本变化
        self.assertEqual(record['last_change'], 'dependency')
        self.assertEqual(record['current']['body']['revid'], 10)
        deps = {d['title']: d['revid'] for d in record['current']['dependencies']}
        self.assertEqual(deps['Template:Capacity'], 21)

    def test_same_run_reflects_template_states_actually_used(self):
        collect_pages(self.client, self.store, [1])
        self.advance()
        collect_pages(self.client, self.store, [2])
        one = self.store.load_page(1)['current']
        two = self.store.load_page(2)['current']
        self.assertIn('2000升', one['expansion']['html'])
        self.assertIn('1800升', two['expansion']['html'])
        self.assertNotEqual(one['content_key'], two['content_key'])

    def test_unprovable_dependencies_keep_distinct_status(self):
        collect_pages(self.client, self.store, [4])
        current = self.store.load_page(4)['current']
        self.assertEqual(current['consistency'], 'partial')
        status = {d['title']: (d['status'], d['revid'])
                  for d in current['dependencies']}
        # 无法证明、循环、权限不足、已删除分别保存，不统一变成空字符串
        self.assertEqual(status['Template:ExternalSpec'], ('unversioned', None))
        self.assertEqual(status['Template:Loop'], ('cycle', None))
        self.assertEqual(status['Template:Internal'], ('denied', None))
        self.assertEqual(status['Template:Removed'], ('deleted', None))
        scan = scan_dependencies(self.client, self.store)
        unverifiable = {entry.get('pageid') for entry in scan['unverifiable']}
        self.assertIn(4, unverifiable)

    def test_unversioned_dependency_is_not_backfilled(self):
        # 来源没给依赖修订，绝不用随后查到的最新修订补成伪快照
        collect_pages(self.client, self.store, [4])
        current = self.store.load_page(4)['current']
        for dependency in current['dependencies']:
            self.assertIsNone(dependency['revid'])

    def test_failed_expansion_does_not_replace_usable_content(self):
        collect_pages(self.client, self.store, [6])
        good = self.store.load_page(6)['current']
        self.advance()
        before = len(self.state['requests'])
        events = collect_pages(self.client, self.store, [6])
        self.assertFalse(events[0]['ok'])
        self.assertTrue(events[0]['kept'])
        record = self.store.load_page(6)
        self.assertEqual(record['current'], good)
        self.assertEqual(len([a for a in record['attempts'] if not a['ok']]), 1)
        # 有限重试：5xx 共尝试 3 次（1 次 + 2 次重试）
        new_requests = self.state['requests'][before:]
        self.assertEqual(new_requests.count('/parse/6?oldid=60'), 3)

    def test_category_only_change_keeps_content_version(self):
        collect_pages(self.client, self.store, [5])
        first = self.store.load_page(5)['current']
        self.advance()
        events = collect_pages(self.client, self.store, [5])
        self.assertEqual(events[0]['change'], 'metadata')
        second = self.store.load_page(5)['current']
        self.assertEqual(first['content_key'], second['content_key'])
        self.assertNotEqual(first['categories'], second['categories'])
        scan = scan_dependencies(self.client, self.store)
        self.assertNotIn(5, scan['stale_pages'])

    def test_redirect_records_alias_and_resolved_identity(self):
        events = collect_pages(self.client, self.store, [3])
        self.assertEqual(events[0]['resolved'], 2)
        record = self.store.load_page(2)
        self.assertIsNotNone(record)
        self.assertEqual(record['aliases'][0]['pageid'], 3)
        self.assertEqual(record['aliases'][0]['title'], '旧型号整机')
        self.assertIsNone(self.store.load_page(3))

    def test_full_incremental_flow(self):
        collect_pages(self.client, self.store, [1, 5, 6])
        self.advance()
        collect_pages(self.client, self.store, [2, 3, 4, 5, 6])
        scan = scan_dependencies(self.client, self.store)
        self.assertEqual(scan['stale_pages'], [1])
        collect_pages(self.client, self.store, scan['stale_pages'])
        final = report(self.store)
        pages = {page['pageid']: page for page in final['pages']}
        # 运营可区分：依赖变化（正文修订不变）
        self.assertEqual(pages[1]['最近变化'], '依赖变化')
        self.assertEqual(pages[1]['正文修订'], 10)
        self.assertIn('1800升', pages[1]['展开结果'])
        self.assertFalse(pages[1]['需要重新领取'])
        # 来源无法提供稳定展开
        self.assertEqual(pages[4]['一致性'], '部分证明')
        self.assertEqual(len(pages[4]['未证明部分']), 4)
        # 失败领取保留可用内容
        self.assertEqual(len(pages[6]['失败尝试']), 1)
        self.assertIn('每六个月', pages[6]['展开结果'])


class DependencyTests(unittest.TestCase):
    def test_normalize_dependency(self):
        self.assertEqual(normalize_dependency({'title': 'T', 'revid': 1}),
                         {'title': 'T', 'status': 'proven', 'revid': 1})
        self.assertEqual(normalize_dependency({'title': 'T'})['status'],
                         'unversioned')
        self.assertEqual(normalize_dependency({'title': 'T', 'error': 'cycle'})['status'],
                         'cycle')

    def test_content_key_ignores_unproven_dependencies(self):
        deps = [{'title': 'A', 'status': 'proven', 'revid': 1},
                {'title': 'B', 'status': 'unversioned', 'revid': None}]
        self.assertEqual(content_key(10, deps), content_key(10, [deps[0]]))
        self.assertNotEqual(content_key(10, deps), content_key(11, deps))

    def test_consistency(self):
        self.assertEqual(consistency_of([{'status': 'proven'}]), 'proven')
        self.assertEqual(consistency_of([{'status': 'cycle'}]), 'partial')
