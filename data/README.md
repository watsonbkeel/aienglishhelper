# 正式词库放置位置

运行 `python3 scripts/prepare_sources.py` 从锁定的 WordMaster_SZ 提交导入，或加 `--dictionary /本地/utils/fullDictionary.js` 使用你已有的开源词库。

将生成 dictionary.json、fullDictionary.js、dictionary-source.json。正式服务在未导入时明确报错，不借用测试词表。
