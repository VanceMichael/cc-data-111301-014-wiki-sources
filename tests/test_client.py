import unittest

from wiki_sources.client import SourceClient, SourceError
from wiki_sources.http_source import source_server


class ClientTests(unittest.TestCase):
    def test_404_fails_without_retry(self):
        with source_server('fixtures') as (address, state):
            client = SourceClient(address)
            with self.assertRaises(SourceError) as failure:
                client.get_bytes('/missing')
            self.assertEqual(failure.exception.status, 404)
            # 确定性状态不重试
            self.assertEqual(state['requests'].count('/missing'), 1)

    def test_5xx_is_retried_with_limit(self):
        with source_server('fixtures') as (address, state):
            client = SourceClient(address)
            client.post_json('/control/advance')
            with self.assertRaises(SourceError) as failure:
                client.get_bytes('/parse/6?oldid=60')
            self.assertEqual(failure.exception.status, 500)
            # 有限重试：共 3 次尝试后放弃
            self.assertEqual(state['requests'].count('/parse/6?oldid=60'), 3)
