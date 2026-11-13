# 本地来源

`wiki_sources.http_source.source_server` 启动仅绑定回环地址的来源服务。端口由系统分配；上下文退出时停止服务。返回的 state 保存当前修订及请求清单，供本地业务联调使用。

## 读取地址

- `/page/1`：{'file': 'page.json'}
- `/parse/1?oldid=10`：[{'file': 'parse-v1.json'}, {'file': 'parse-v2.json'}]
- `/template/Capacity`：[{'file': 'template-v1.json'}, {'file': 'template-v2.json'}]

同一路径可以配置多个来源修订。`POST /control/advance` 只在演练服务中存在，用来推进来源状态，不属于生产站点接口。不存在的路径返回 404；ETag 对应的条件请求可以返回 304。返回正文均来自对应文件，不由采集逻辑生成。
