"""来源读取：有限重试，只对可能瞬时的失败重试。

重试条件（有限重试）：
- 仅传输错误与 HTTP 429/5xx 可重试，最多 2 次（共 3 次尝试），间隔随次数递增。
- 其余 4xx（404 不存在或已删除、403 权限不足等）属于确定性状态，立即失败，不重试。
"""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SourceError(Exception):
    """来源读取失败。status 为 HTTP 状态码；传输错误为 None。"""

    def __init__(self, path, status, detail):
        self.path = path
        self.status = status
        self.detail = detail
        label = status if status is not None else '传输错误'
        super().__init__(f'{path} 读取失败（{label}）：{detail}')


class SourceClient:
    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(self, base, retries=2, backoff=0.1, timeout=5):
        self.base = base.rstrip('/')
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout

    def get_bytes(self, path):
        attempt = 0
        while True:
            try:
                with urlopen(self.base + path, timeout=self.timeout) as response:
                    return response.read()
            except HTTPError as failure:
                if failure.code in self.RETRYABLE_STATUS and attempt < self.retries:
                    attempt += 1
                    time.sleep(self.backoff * attempt)
                    continue
                raise SourceError(path, failure.code, f'HTTP {failure.code}') from failure
            except URLError as failure:
                if attempt < self.retries:
                    attempt += 1
                    time.sleep(self.backoff * attempt)
                    continue
                raise SourceError(path, None, str(failure.reason)) from failure

    def get_json(self, path):
        return json.loads(self.get_bytes(path).decode('utf-8'))

    def post_json(self, path, data=b''):
        request = Request(self.base + path, data=data, method='POST')
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode('utf-8'))
