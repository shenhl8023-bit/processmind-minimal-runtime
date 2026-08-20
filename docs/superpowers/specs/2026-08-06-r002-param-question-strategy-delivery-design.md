# R-002 参数问答策略交付一致性设计

## 目标

消除后端从前端源码目录读取参数问答策略造成的部署差异，使本地运行、Docker API、Docker Web 和 Windows 离线包使用同一份策略内容和稳定版本。

## 方案

将 `process-plan-agent-ui/src/config/paramQuestionStrategy.json` 迁移为 `docs/配置模板/第五步参数问答策略.json`，保留现有 JSON 结构并增加 `version` 字段。后端通过 `app.core.paths.PARAM_QUESTION_STRATEGY_PATH` 读取共享文件，前端通过相对路径原始 JSON 导入同一文件。Dockerfile.api、Dockerfile.web 显式复制该文件；现有离线打包脚本已递归携带 `docs/`，通过交付测试锁定该文件不会被遗漏。

后端加载器提供显式 `path` 注入能力供测试使用，默认路径只来自 `app.core.paths`。配置缺失、JSON 无法解析或顶层结构不符合策略契约时抛出带路径和原因的明确异常，不再返回空字典并静默启用硬编码策略。API lifespan 在数据库初始化前执行该校验，确保正式运行环境启动失败而不是运行到问答请求时才漂移。

## 契约

- `version`：非空字符串，前后端必须读取同一值。
- `familyRules`：数组；每项包含非空 `family`、`label` 和字符串数组 `patterns`。
- `rootReasonPriority`：对象；每个值为字符串数组。
- `terminalQuestionTypes`：字符串数组。
- 旧的前端 JSON 文件删除，仓库中不保留兼容读取路径。

## 测试

- 后端加载器使用临时文件验证有效配置、缺失配置、非法 JSON 和非法结构；验证显式路径注入不触碰前端源码目录。
- 启动生命周期在配置无效时失败，并在数据库初始化前报告策略错误。
- 交付测试验证共享文件、API/Web Docker COPY、旧路径删除以及离线 staging 会携带共享配置。
- 前端生产构建和现有前端测试验证新的相对 JSON 导入及版本字段类型。

## 不变范围

不改变问答策略的分类、排序、终止题型或 API 响应语义；不修改 V2/V1 规则包协议、数据库结构和 KmAI 导出内容。
