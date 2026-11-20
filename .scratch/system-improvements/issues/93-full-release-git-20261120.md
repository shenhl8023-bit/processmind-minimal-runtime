# PM-093：提交推送当前修复版并交付完整包

Status: done
Execution: implemented-and-verified-20261120; full-release-and-git-push
Updated: 2026-11-20
Related: PM-038, PM-089, PM-091, PM-092

## 用户授权

用户要求“把这个上传到git，然后给我打一个新包”。授权将当前修复版提交并推送既有origin/codex/zhaoyw分支，打full完整包。包含此前未提交的PM-091导出/接收器兼容修复及本轮PM-092/038修复；不包含无关文件、正式数据、模型密钥或运行时二进制入Git。

## 执行清单

- [x] 完整前后端测试、生产构建、Python3.8静态语法及差异检查。
- [x] 从可信旧完整包原样重用Windows运行时，清洁staging加入当前源码、前端产物、full配置和KmAI读取器。
- [x] 验证文件清单、逐文件SHA256、运行时及ZIP完整性；隔离启动交付API和静态前端。
- [x] 检查提交清单和敏感信息，提交当前版本并正常推送；核对远程提交一致。
- [x] 记录压缩包路径、摘要、Git提交和实机验证限制，更新总账。

## 约束

保持Win7 Pro/SP1 x64、Python3.8.10、Chrome109目标。完整包包含导入/映射/编排能力，并保留管理员当前隐藏第六步的product-features配置。正式数据及模型设置保留；PM-065继续deferred。当前macOS不能替代Win7实机验收。

## Answer

产品提交20444657cf8a9a03f25fdf9b76143634ff5b20c0已推送origin/codex/zhaoyw并核对远端。完整包`dist-win7/processmind-win7-full-template-20261120-pm092.zip`，46,434,947字节、2277文件，SHA256为97381a7cf937443f9aa13b0de836f359905f89c8bcdb3ac2f0a6c5ac665a88a1。1967个Windows运行时文件保持，源码/前端/摘要/解压验证及隔离启动通过；后端2294 passed/111 skipped、前端1418 passed/1 skipped、构建及Python3.8静态检查通过。正式数据与配置摘要未变；Win7实机尚未验证。详见[交付验收](../../../docs/superpowers/reviews/2026-11-20-full-release-acceptance.md)。交付记录随独立文档提交同步，不改变包内产品源码。
