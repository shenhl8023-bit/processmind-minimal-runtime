# KmAI三表读取器更新：特征参数条件必填

适用于ProcessMind PM-091修复后的三表规则包。三个文件名和顶层数组保持不变；因素表增加可选`required_when`条件，例如：

```json
{
  "key": "F002",
  "label": "平面的方位",
  "type": "enum",
  "options": ["A侧", "B侧", "所有方位"],
  "source": "manual_defaults.F002",
  "visible": true,
  "default": null,
  "required_when": {"field": "F001", "op": "eq", "value": true}
}
```

`F001`是是否选择平面的布尔因素。未选择时无需填写F002；选择后缺少F002时生成失败并提示因素名称。IT与Ra同样按对应特征要求填写。规则包仍包含完整母路线和条件，不把当前验证零件的勾选状态固定进规则包。

## 更新接收电脑

1. 关闭接收系统，备份`KmMpsMcpServer/skills/process-route-generator/scripts/config_route_engine.py`。
2. 使用本目录同名文件替换该文件，重启接收系统，再导入新导出的三个JSON文件。
3. 用未勾选特征、已勾选但缺少方位、参数完整三种输入检查；第二种应提示缺项。

本文件基于当前本机KmAI读取器，仅补充条件必填支持；其它版本如已有定制代码，应合并补丁而非直接覆盖。Python3.8语法与标准库保持兼容。未含此字段的旧包继续使用原静态`required`。

新包需要配套读取器：旧读取器可能忽略未知字段，不能以成功导入作为已支持条件必填的证据。接收端参数预览保留`required_when`，允许预览尚未填写的参数；实际生成会执行校验。条件不能引用`selected_processes`、逐行CAD条件`some`或数组取值来源。
