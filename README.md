# 知识站模板展开资料的修订依据资料工具

这个 Python 项目用于业务来源资料的检查、原始字节归档与模板展开资料的修订依据采集。`wiki_sources/core.py` 处理现有资料预览，`archive.py` 保存原文件，`client.py`/`store.py`/`collect.py` 负责领取采集与增量更新，`fixtures/` 保存本地业务演练资料，`tests/` 检查已有行为。

## 环境

Python 3.11.2。依赖及其间接依赖固定在 `requirements.txt`；空清单表示只使用标准库。安装只在环境准备阶段执行：

```sh
python3 -m pip install -r requirements.txt
```

## 运行

```sh
python3 -m wiki_sources inspect fixtures/page.json
python3 -m wiki_sources capture fixtures/page.json --archive .work/raw
python3 -m wiki_sources collect --source http://127.0.0.1:8000 --store .work/store 1 2 3
python3 -m wiki_sources scan --source http://127.0.0.1:8000 --store .work/store
python3 -m wiki_sources report --store .work/store
```

归档返回 SHA-256、字节数及原文件名；文件名不参与内容身份。预览只说明单份来源的基本结构，不代表关联资料已经齐全。输入不可识别时命令失败，不产生空的成功结果。

`collect` 领取页面正文与来源展开结果：请求的正文修订、实际展开结果、来源可证明的依赖修订分别保存，下游不再把正文修订号误当成整个页面的内容版本。`scan` 只核对已证明依赖的当前修订，找出需要重新领取的页面；普通分类变化不参与版本判定。`report` 呈现各页内容版本、一致性、未证明部分与失败尝试。一致性承诺与有限重试条件见 `docs/consistency.md`。

## 开发检查

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q wiki_sources tests
```

## 本地演示

```sh
python3 -m wiki_sources demo
```

演示实际读取来源资料：领取期间来源推进一次共享模板修订（正文修订不变），输出可见同一轮领取中各页实际用到的展开结果、受模板更新影响而需要重新领取的页面、重新领取后的复查，以及来源无法证明的依赖部分。使用临时目录并自动清理。所有示例身份与业务数值均为虚构，不需要外部账号。
