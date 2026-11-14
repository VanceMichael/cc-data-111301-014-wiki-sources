# 本地来源

`wiki_sources.http_source.source_server` 启动仅绑定回环地址的来源服务。端口由系统分配；上下文退出时停止服务。返回的 state 保存当前修订及请求清单，供本地业务联调使用。

## 读取地址

- `/page/1` … `/page/6`：六个演练页面；`/page/3` 经重定向解析到页面 2。
- `/parse/1?oldid=10`、`/parse/2?oldid=15`：两个版本，随来源状态从 Template:Capacity 修订 20 切到 21。
- `/parse/4?oldid=40`：含无法证明、循环、权限不足、已删除四类依赖。
- `/parse/5?oldid=50`：两个版本仅分类不同，用于验证分类变化不产生新内容版本。
- `/parse/6?oldid=60`：来源状态推进后返回 500，用于演练失败领取不覆盖可用内容。
- `/template/Capacity`：两个版本（修订 20、21）。
- `/template/Manual`、`/module/Conversion`：单版本。

同一路径可以配置多个来源修订。`POST /control/advance` 只在演练服务中存在，用来推进来源状态，不属于生产站点接口。不存在的路径返回 404；ETag 对应的条件请求可以返回 304。返回正文均来自对应文件，不由采集逻辑生成。
