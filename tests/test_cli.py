import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CommandTests(unittest.TestCase):
    def test_preview_and_raw_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run([sys.executable,'-m','wiki_sources','demo'],capture_output=True,text=True,timeout=15)
            self.assertEqual(process.returncode,0,process.stderr)
            result = json.loads(process.stdout)
            self.assertIn('资料预览',result)
            self.assertGreater(result['原始资料']['bytes'],0)
            self.assertEqual(len(result['原始资料']['sha256']),64)

    def test_demo_collection_drill(self):
        process = subprocess.run([sys.executable,'-m','wiki_sources','demo'],capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stderr)
        drill = json.loads(process.stdout)['采集演练']
        # 受影响页面：共享模板更新后只有页面 1 需要重新领取
        self.assertEqual(drill['受影响页面'],[1])
        before = {event['requested']:event for event in drill['模板更新前领取']}
        after = {event['requested']:event for event in drill['模板更新后领取']}
        # 实际用到的结果：同一轮领取中模板更新前后各页用到的展开
        self.assertIn('2000升',before[1]['expansion'])
        self.assertIn('1800升',after[2]['expansion'])
        # 失败的展开不替换当前可用内容
        self.assertFalse(after[6]['ok'])
        self.assertTrue(after[6]['kept'])
        # 重定向解析到实际条目
        self.assertEqual(after[3]['resolved'],2)
        pages = {page['pageid']:page for page in drill['最终报告']['pages']}
        # 没有被证明的部分：四种状态分别保存
        statuses = {item['状态'] for item in pages[4]['未证明部分']}
        self.assertEqual(statuses,{'无法证明','循环','权限不足','已删除'})
        self.assertEqual(pages[1]['最近变化'],'依赖变化')
