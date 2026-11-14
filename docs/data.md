# 来源资料约定

本地来源仅模拟本文使用的 MediaWiki 风格端点，不声称实现完整 MediaWiki。

## 端点

- `/page/<id>`：页面正文。响应含 pageid、title、revid、text。重定向页由来源直接解析到实际条目，并带 `redirect: {from_pageid, from_title}` 说明请求标识与实际条目的对应关系。
- `/parse/<id>?oldid=<revid>`：来源对指定正文修订的实际展开结果，含 html、categories 与 dependencies。oldid 固定正文，但并不自动冻结模板。
- `/template/<名称>`、`/module/<名称>`：模板/数据模块的当前修订，仅供增量扫描核对新鲜度，不用于补全快照。
- `POST /control/advance`：只在演练服务中存在，用来推进来源状态（正文修订不变，模板和展开内容变化），不属于生产站点接口。

## 依赖条目

parse 响应的 dependencies 是来源在展开时实际使用并有能力声明的依赖，包括模板嵌套的模板与数据模块：

- `{"title": ..., "revid": ...}`：来源可证明的依赖修订。
- `{"title": ...}`：来源使用了该依赖但给不出修订。采集侧记为 unversioned（无法证明），不得用事后查到的最新修订补成伪快照。
- `{"title": ..., "error": "cycle"|"denied"|"deleted"}`：循环、权限不足、已删除。三种状态分别保存，不统一压成空字符串。

不存在的路径返回 404；ETag 对应的条件请求可以返回 304。返回正文均来自对应文件，不由采集逻辑生成。
