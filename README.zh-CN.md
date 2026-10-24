# redirect-map-audit 中文说明

网站迁移前，离线检查永久重定向 CSV。结合旧站与新站路径清单，发现下线路径漏配、最终目标不存在、循环、重复来源及自重定向。通过后可导出单跳映射。运行时仅需 Python 3.10+ 标准库。

```sh
python -m pip install .
python -m redirect_map_audit examples/good.csv --old-paths examples/old.txt --new-paths examples/new.txt --flatten flattened.csv --json
python -m redirect_map_audit examples/bad.csv --json
```

首条退出 0 并导出，第二条退出 1。若输出文件已存在则退出 2，不覆盖。CSV 表头为 `source,target` 或 `source,target,status`；支持 301/308，混合两种状态的链会保守拒绝折叠。所有错误消除前不会导出不完整的“修复结果”。

路径严格区分大小写、尾斜杠、查询串和百分号编码。`--origin` 将同源绝对 URL 转为站内路径，外部目标需显式 `--allow-origin`。不解释通配符、正则或服务器重写规则，不请求网络，也不能证明线上页面可达。

清单每行一个路径；新清单应列出实际提供内容的页面，不包括中间重定向源。旧清单减去新清单所得的下线路径必须有映射，站内最终目标必须存在于新清单。

报告包含路径和查询串，分享前应检查是否有私人内容。完整匹配规则、资源上限、安装、测试和清理说明见 [英文 README](README.md)。卸载：`python -m pip uninstall redirect-map-audit`；工具不存储缓存。
