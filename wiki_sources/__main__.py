DESCRIPTION = '知识站模板展开资料的修订依据采集'
SAMPLE = 'fixtures/page.json'

import argparse
import json
from pathlib import Path

from .archive import archive_file
from .client import SourceClient
from .collect import collect_pages, report, scan_dependencies
from .core import inspect_file
from .demo import run_demo
from .store import Store


def main():
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    commands = parser.add_subparsers(dest='command', required=True)

    inspect_cmd = commands.add_parser('inspect', help='预览单份来源资料')
    inspect_cmd.add_argument('path', nargs='?', default=SAMPLE)

    capture_cmd = commands.add_parser('capture', help='归档原始字节')
    capture_cmd.add_argument('path', nargs='?', default=SAMPLE)
    capture_cmd.add_argument('--archive', default='.work/raw')

    collect_cmd = commands.add_parser('collect', help='领取页面，保存展开结果与依赖依据')
    collect_cmd.add_argument('--source', required=True)
    collect_cmd.add_argument('--store', default='.work/store')
    collect_cmd.add_argument('pages', nargs='+', type=int)

    scan_cmd = commands.add_parser('scan', help='核对依赖修订，找出需要重新领取的页面')
    scan_cmd.add_argument('--source', required=True)
    scan_cmd.add_argument('--store', default='.work/store')

    report_cmd = commands.add_parser('report', help='输出仓库状态报告')
    report_cmd.add_argument('--store', default='.work/store')

    commands.add_parser('demo', help='本地演练：领取期间来源更新一次共享模板')

    args = parser.parse_args()
    if args.command == 'inspect':
        result = inspect_file(Path(args.path))
    elif args.command == 'capture':
        result = archive_file(Path(args.path), Path(args.archive))
    elif args.command == 'collect':
        events = collect_pages(SourceClient(args.source), Store(Path(args.store)),
                               args.pages)
        result = {'events': events}
    elif args.command == 'scan':
        result = scan_dependencies(SourceClient(args.source), Store(Path(args.store)))
    elif args.command == 'report':
        result = report(Store(Path(args.store)))
    else:
        result = run_demo()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
