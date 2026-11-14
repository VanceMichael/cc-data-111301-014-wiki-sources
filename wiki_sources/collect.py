"""领取采集：请求的正文修订、实际展开结果、来源可证明的依赖修订分别保存。

一致性承诺（详见 docs/consistency.md）：
- 单页快照内部一致：三者取自同一 oldid 的同一次 parse 响应，原始字节各自归档。
- 内容版本只由正文修订与已证明依赖修订决定；分类等附属信息不参与。
- 来源给不出依赖修订时记为无法证明，不用事后查到的最新修订补成伪快照。
- 展开失败只追加失败尝试，不替换当前可用内容。
"""

import hashlib
import json
from datetime import datetime, timezone

from .client import SourceError
from .store import new_record

STATUS_LABEL = {'proven': '已证明', 'unversioned': '无法证明',
                'cycle': '循环', 'denied': '权限不足', 'deleted': '已删除'}

CHANGE_LABEL = {'initial': '首次领取', 'body': '正文变化', 'dependency': '依赖变化',
                'metadata': '附属信息变化', 'unchanged': '无变化'}

CONSISTENCY_LABEL = {'proven': '已证明', 'partial': '部分证明'}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _text_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def normalize_dependency(entry):
    """规范化来源 parse 断言的一条依赖。

    来源给出 revid → proven；既无 revid 也无错误 → unversioned（无法证明）；
    来源报告的错误状态（cycle/denied/deleted）分别保留，不统一压成空值。
    """
    if 'error' in entry:
        return {'title': entry['title'], 'status': entry['error'], 'revid': None}
    if 'revid' in entry:
        return {'title': entry['title'], 'status': 'proven', 'revid': entry['revid']}
    return {'title': entry['title'], 'status': 'unversioned', 'revid': None}


def content_key(body_revid, dependencies):
    """内容版本材料：正文修订 + 已证明依赖修订。无法证明的依赖不进入版本，
    它们把一致性降为部分证明，但不伪造版本材料。"""
    proven = {dependency['title']: dependency['revid']
              for dependency in dependencies if dependency['status'] == 'proven'}
    material = json.dumps({'body': body_revid, 'deps': proven},
                          sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(material.encode('utf-8')).hexdigest()


def consistency_of(dependencies):
    if all(dependency['status'] == 'proven' for dependency in dependencies):
        return 'proven'
    return 'partial'


def classify_change(previous, snapshot):
    """区分正文变化与依赖变化，供运营判断“同一修订号看到不同内容”的来源。"""
    if previous is None:
        return 'initial'
    if previous['content_key'] == snapshot['content_key']:
        if previous.get('categories') != snapshot.get('categories'):
            return 'metadata'
        return 'unchanged'
    if previous['body']['revid'] != snapshot['body']['revid']:
        return 'body'
    return 'dependency'


def dependency_summary(dependencies):
    items = []
    for dependency in dependencies:
        if dependency['status'] == 'proven':
            items.append(f"{dependency['title']}@{dependency['revid']}")
        else:
            items.append(f"{dependency['title']}#{STATUS_LABEL[dependency['status']]}")
    return items


def dependency_path(title):
    for prefix, route in (('Template:', '/template/'), ('Module:', '/module/')):
        if title.startswith(prefix):
            return route + title[len(prefix):]
    return None


def collect_page(client, store, requested):
    """领取一个页面。requested 是请求的页面标识，可经重定向解析到实际条目。"""
    at = _now()
    event = {'requested': requested, 'at': at}
    try:
        raw_page = client.get_bytes(f'/page/{requested}')
    except SourceError as failure:
        event.update(ok=False, stage='page', error=str(failure))
        return event
    page = json.loads(raw_page.decode('utf-8'))
    resolved = page['pageid']
    redirect = page.get('redirect')
    page_digest = store.archive(raw_page)
    event['resolved'] = resolved
    if redirect:
        event['redirect'] = redirect

    record = store.load_page(resolved) or new_record(resolved, page['title'])
    record['title'] = page['title']
    if redirect and not any(alias['pageid'] == requested for alias in record['aliases']):
        record['aliases'].append({'pageid': requested,
                                  'title': redirect.get('from_title'), 'at': at})
    try:
        raw_parse = client.get_bytes(f"/parse/{resolved}?oldid={page['revid']}")
    except SourceError as failure:
        record['attempts'].append({'at': at, 'ok': False, 'stage': 'parse',
                                   'page_raw': page_digest,
                                   'error': {'status': failure.status,
                                             'detail': str(failure)}})
        store.save_page(record)
        event.update(ok=False, stage='parse', error=str(failure),
                     kept=record['current'] is not None)
        return event
    parse = json.loads(raw_parse.decode('utf-8'))
    if parse.get('pageid') != resolved or parse.get('revid') != page['revid']:
        # 展开与请求的正文修订对不上：记失败，绝不用它覆盖可用内容。
        detail = f"展开修订 {parse.get('revid')} 与正文修订 {page['revid']} 不一致"
        record['attempts'].append({'at': at, 'ok': False, 'stage': 'parse',
                                   'page_raw': page_digest,
                                   'error': {'status': None, 'detail': detail}})
        store.save_page(record)
        event.update(ok=False, stage='parse', error=detail,
                     kept=record['current'] is not None)
        return event

    parse_digest = store.archive(raw_parse)
    dependencies = [normalize_dependency(entry) for entry in parse.get('dependencies', [])]
    snapshot = {
        'collected_at': at,
        'requested': {'pageid': requested, 'redirect': redirect},
        'body': {'revid': page['revid'], 'text': page['text'],
                 'sha256': _text_digest(page['text']), 'raw': page_digest},
        'expansion': {'html': parse['html'], 'sha256': _text_digest(parse['html']),
                      'raw': parse_digest},
        'categories': parse.get('categories', []),
        'dependencies': dependencies,
        'consistency': consistency_of(dependencies),
        'content_key': content_key(page['revid'], dependencies),
    }
    previous = record['current']
    change = classify_change(previous, snapshot)
    if previous is not None and change in ('unchanged', 'metadata'):
        # 内容版本未变：只更新附属信息，不产生新版本，不触发下游重抓。
        previous['categories'] = snapshot['categories']
        previous['collected_at'] = at
    else:
        if previous is not None:
            record['history'].append(previous)
        record['current'] = snapshot
    record['last_change'] = change
    record['stale'] = False
    record['stale_reasons'] = []
    record['attempts'].append({'at': at, 'ok': True, 'change': change})
    store.save_page(record)
    event.update(ok=True, change=change, consistency=snapshot['consistency'],
                 revision=page['revid'], expansion=parse['html'],
                 dependencies=dependency_summary(dependencies))
    return event


def collect_pages(client, store, requested_ids):
    return [collect_page(client, store, pageid) for pageid in requested_ids]


def scan_dependencies(client, store):
    """增量扫描：只核对已证明依赖的当前修订，找出需要重新领取的页面。

    不重抓整页；分类变化不参与；无法证明的依赖无法核对，单列说明。
    """
    index = store.dependency_index()
    report = {'checked': [], 'stale_pages': [], 'unverifiable': [], 'errors': []}
    stale = {}
    for title in sorted(index):
        path = dependency_path(title)
        if path is None:
            report['unverifiable'].append({'title': title,
                                           'reason': '该命名空间没有查询端点'})
            continue
        try:
            data = client.get_json(path)
        except SourceError as failure:
            report['errors'].append({'title': title, 'error': str(failure)})
            continue
        current = data.get('revid')
        affected = sorted(pageid for pageid, revid in index[title].items()
                          if revid != current)
        report['checked'].append({'title': title, 'current': current,
                                  'affected': affected})
        for pageid in affected:
            stale.setdefault(pageid, []).append(
                {'title': title, 'recorded': index[title][pageid], 'current': current})
    for record in store.all_pages():
        reasons = stale.get(record['pageid'], [])
        record['stale'] = bool(reasons)
        record['stale_reasons'] = reasons
        store.save_page(record)
        current = record.get('current')
        if current:
            unproven = [dependency for dependency in current['dependencies']
                        if dependency['status'] != 'proven']
            if unproven:
                report['unverifiable'].append({
                    'pageid': record['pageid'],
                    'dependencies': dependency_summary(unproven),
                    'reason': '来源未提供可核对的依赖修订，无法验证新鲜度'})
    report['stale_pages'] = sorted(stale)
    return report


def report(store):
    """运营报告：区分正文变化、依赖变化与来源无法提供稳定展开的情形。"""
    pages = []
    for record in store.all_pages():
        current = record.get('current')
        entry = {
            'pageid': record['pageid'],
            '标题': record['title'],
            '别名': [{'pageid': alias['pageid'], '标题': alias.get('title')}
                    for alias in record['aliases']],
            '最近变化': CHANGE_LABEL.get(record.get('last_change'),
                                       record.get('last_change')),
            '需要重新领取': record['stale'],
            '过期依据': record['stale_reasons'],
            '失败尝试': [attempt for attempt in record['attempts'] if not attempt['ok']],
            '历史版本数': len(record['history']),
        }
        if current:
            unproven = [dependency for dependency in current['dependencies']
                        if dependency['status'] != 'proven']
            entry.update({
                '正文修订': current['body']['revid'],
                '内容版本': current['content_key'][:12],
                '一致性': CONSISTENCY_LABEL[current['consistency']],
                '展开结果': current['expansion']['html'],
                '分类': current['categories'],
                '依赖': [{'标题': dependency['title'],
                         '状态': STATUS_LABEL[dependency['status']],
                         '修订': dependency['revid']}
                        for dependency in current['dependencies']],
                '未证明部分': [{'标题': dependency['title'],
                            '状态': STATUS_LABEL[dependency['status']]}
                           for dependency in unproven],
                '依据': {'正文对象': current['body']['raw'],
                       '展开对象': current['expansion']['raw']},
            })
        else:
            entry['可用内容'] = '无'
        pages.append(entry)
    return {'pages': pages}
