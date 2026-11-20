# 2026-11-20 完整包与Git交付验收

用户授权：将当前版上传Git并打新包。按项目AGENTS使用full配置，包含分组模板导入、映射、编排及本轮PM-092/038和此前PM-091修复。

## 源码与远程

产品提交：`20444657cf8a9a03f25fdf9b76143634ff5b20c0`，主题`fix: harden model responses and conditional rule exports`。已推送到既有仓库`shenhl8023-bit/processmind-minimal-runtime`的`codex/zhaoyw`分支，`git ls-remote`确认一致。未合并main、未强制推送、未创建发布或PR。原11月17日本地提交d459731随既有分支一并正常推送。

提交包含产品代码、真实缺陷回归、KmAI配套读取器和相关设计/验收记录。无关的个人文件、历史未追踪材料、正式数据库/PDF/密钥及交付ZIP未加入Git。

## 完整包

- 路径：`dist-win7/processmind-win7-full-template-20261120-pm092.zip`
- 大小：46,434,947字节，2277个文件。
- SHA256：`97381a7cf937443f9aa13b0de836f359905f89c8bcdb3ac2f0a6c5ac665a88a1`
- 源码版本在包内manifest.json标记为上述2044465；API及接收器156个文件逐字节核对Git提交，前端/配置/其它交付源码与本次最终构建、工作区逐文件摘要一致。
- 从已验证的20261108完整包原样取出1967个Windows运行时文件；逐文件摘要、CPython3.8.10官方核心、固定依赖和Win7已知不兼容依赖扫描通过。未使用开发机Python3.13运行时替代交付运行时。
- full、无到期时间，导入/映射/编排API与代码完整包含；保留`product-features.json`中当前隐藏第六步的配置。启用方法见包内使用说明。
- 含`integrations/kmai`读取器及PM-091更新说明；另一电脑的接收系统仍须按说明单独更新，旧读取器不会自动升级。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| 后端完整回归 | 2294 passed / 111 skipped，52.21秒；15条已有依赖/弃用警告 |
| 前端完整回归 | 1418 passed / 1 skipped，93个文件通过 |
| TypeScript及生产构建 | 通过，Chrome109目标 |
| Python3.8源码检查 | 应用150个文件、接收器1个文件通过；解压后同样通过 |
| 包验证器 | staging及最终ZIP解压目录均通过 |
| ZIP和摘要 | CRC、2277个归档文件与staging逐字节摘要通过 |
| 隔离启动 | 从ZIP解压的API启动成功；初始任务为空、无已配置密钥；静态页面、2个入口资源及浏览器HTML路由通过 |
| 包内修复生效 | 隔离MockTransport验证空正文一次恢复成功，未调用真实模型 |
| 正式数据保护 | 本轮结束正式数据库与模型设置SHA256仍和修复前相同 |

解压启动初次脚本以默认`Accept: */*`测试SPA深层路由而失败；核对既有静态服务要求HTML Accept后，按浏览器实际`Accept: text/html`重验通过。仅修正验证请求，没有修改产品以迁就脚本。

证据：`.scratch/system-improvements/evidence/pm-093/`内`package-verification.json`、`package-smoke.json`、`release-verification.json`及可重复的`build_release.py`；测试日志位于`.runtime/pm092-model-response/release-api-tests.log`、`release-ui-tests.log`及`.runtime/release-20261120/build.log`。

本轮macOS不能执行Windows原生程序；Win7 SP1 x64实机验收仍待客户机器执行。本机真实模型连接和第三至第五步在前一修复验收中通过，但模型服务仍可能偶发超时；本次打包没有再重复完整模型请求。正式8000/5173服务保留，PM-065仍deferred。
