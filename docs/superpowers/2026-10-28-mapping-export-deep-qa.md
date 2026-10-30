# 模板映射至规则包导出：第二轮深度审查

日期：2026-10-28。范围：模板映射保存、规则修改、发布预检、历史包、最终三文件及实际下游执行。所有业务修改测试在临时数据库/真实数据副本进行；真实项目5及既有发布包2/V2保持不变。

## 本轮实际修复

| 范围 | 复现的问题 | 修复与回归 |
|---|---|---|
| 增量映射 | replace_all=false空请求清空已有映射 | 合并保留已有决定；最终树删除、移动工步、更换来源时收敛旧目标 |
| 最终树 | 省略operations把最终ID、精度降级回来源树 | 已有最终树要求完整最终路线；保存前拒空白名称及辅助工序非法精度 |
| 跨页面竞态 | 重生成后revision重新从1开始，旧页面覆盖新树 | 三写端增加workflow revision事务锁；UI贯穿路线版本；流程冲突要求整页重载，禁止旧草稿写回 |
| 工作流锁 | ORM缓存使冲突报告或锁定后对象仍是旧版本 | populate_existing；真实双session覆盖冲突及成功两分支 |
| 自动样例 | 数字越界；同字段被exists覆写；any/not首分支冲突；集合长度忽略 | 同字段数值/离散/集合联合取值，有界分支回溯；原规则不改，超预算仍阻止发布 |
| Bool和取反 | eq false生成相反伴随动作；not(exists)缺字段语义不一致 | 仅eq true补false规则；显式null和缺字段保护与后端一致 |
| 发布异步 | onPrecheck切项目仍发发布请求 | 回调后再次校验有效性；重复点击仅一次编译/发布/下载 |
| 数值/输入 | float混同大整数；NaN/Inf及极大整数可能500 | 保留整数比较精度；非法数值给结构化错误；有效大数保持类型 |
| 覆盖率 | 接受别名但覆盖率仍用原值 | 统一canonical inputs；外部三表枚举仍需规范选项原值 |
| CAD来源 | 重复scalar来源误导出multi_enum；归一化丢盲/通孔和路径语义 | 按来源导出元素类型；无法无损表示时精确阻断 |
| 抽象类别和真实几何 | cad.features抽象类别绑真实feature_select，导致拒值/工步无法绑定 | 新导出cad.features为可见manual_defaults.cad.features多选；真实feature_type仍CAD、工步候选仍真实几何；没有编造自动分类 |
| 历史下载 | reset解除FK或编译行为更新误拒合法冻结包 | 按冻结manifest身份校验；新版本/2绑定native hash；无绑定/1以两个已证固定历史profile（均支持工序配置、不同可选标量默认值）重编译自身冻结路线，篡改仍拒 |

## 实际浏览器验收

隔离API8010、UI5180；复制原数据库及上传文件并保留mtime。未在真实项目写测试状态。

1. 精度修改后取消，再进入仍原值；保存PUT200、revision4到5、workflow2，刷新保留新值。
2. 精度留空保存被明确提示钻中间孔，没有静默发布。
3. 正常化材料条件改6061并保存200，刷新保持。
4. 将去应力改前置要求后发布，预检指出钻中间孔、去应力和第1项关联；定位按钮正确滚动卡片，修回仅调整顺序并保存。
5. 发布V4返回200，compiler=demo-three-table/2。真实下载ZIP检查CRC、UTF-8和JSON数组，恰好factor_table.json(12行)、full_route_table.json(38道工序)、rule_table.json(38行)，与本次冻结快照完全相同。
6. 实际ConfigRouteEngine加载下载三JSON，提供全部候选的真实几何和明确人工分类，执行18个样例，全部与native工序名称及顺序相符；同名隔离另有ID级矩阵回归。
7. 进入验证生成、填示例、生成POST200，返回规则包版本、选择工序、工步、完整路线结构。

## 最终验证

- API：1052 passed，9 skipped，10 warnings，19.97秒。
- UI：51文件、522 passed，2.04秒；npm run build通过。
- Python3.8扫描128文件通过；当前运行Python3.13，并非Windows实机。
- 7600次真实下游混合条件差分，三文件分别JSON往返，另含非法值及同名ID隔离。
- 前端6类样例独立经真实后端编译/覆盖率/条件求值，valid=true且matched=true。
- 本轮修改文件diff检查通过；既有FeatureTemplate.xml CRLF尾空白未做无关改动。

9项skip为Windows PowerShell/重解析点相关；本轮无Windows7实机测试。10项warning来自既有依赖及datetime弃用。

## 可重复证据

outputs/mapping-export-deep-qa-20261028包含日志、browser-export-v4.zip、browser-package-v4.json、browser-export-verification.json、original-data-unchanged.json和verify_browser_zip.py。

在API目录执行 PYTHONPATH=. .venv/bin/python ../outputs/mapping-export-deep-qa-20261028/verify_browser_zip.py。脚本使用本机既有实际ConfigRouteEngine路径。测试证据不含模型设置/凭据，隔离设置副本结束时删除、隔离服务停止。

## 明确边界

- 抽象CAD类别由用户或上游已审定分类器提供，现为可见明确输入，没有声称从几何名自动推断所有加工类别。
- 三表枚举协议没有alias字段，需规范options原值；native接口仍支持别名归一化。
- optional取反/不等、数值容差相等、互斥等外部引擎无法无损表达的情况仍明确阻断，不静默改写。
- 自动样例分支预算256、集合预算4096，不宣称任意约束可求解。
- 哈希用于一致性/防混版本，并非抵御数据库任意写权限的数字签名。
- 既有发布包保持冻结；最新编译修复通过重新发布新版本使用。

最终真实服务重启后再次GET核对：项目5 workflow_revision=2、模板revision=4、原发布包2/V2的native hash、三文件内容、来源快照全部与测试前相同；补入三份真实历史DTO和21条兼容/篡改回归。隔离服务已停止，临时模型设置已删除。


## 最终完成审计

重新依据当前工作树执行全量验证，而非复用上一轮结果：API 1052 passed/9平台skip；UI 522 passed；构建通过；Python3.8扫描128文件通过；实际浏览器下载V4归档18例再次执行通过。原服务页面只读确认V2、25/25已确认、发布按钮可用，API逐项核对原映射、原三文件、native hash、来源版本未变，export_error为空。

| 原计划要求 | 当前证据 | 结论 |
|---|---|---|
| 隔离环境与原数据基线 | before-template/package及completion-runtime-proof.json；临时配置已删除、隔离监听已停止 | 完成 |
| 浏览器保存/刷新/取消/精度提醒/错误定位 | 本文7项实际验收记录，API保存回归及UI映射/预检专项；当前真实页面V2/25/25只读确认 | 完成 |
| API版本/树变更/重复发布/审定一致性 | test_project_group_template_api、test_rule_package_lifecycle、test_workflow_invalidation、test_workflow_progress | 完成 |
| 布尔/枚举/集合/数值/关联语义 | test_demo_differential_matrix的7600次实际下游执行，ID隔离与条件专项 | 完成 |
| ZIP恰好三JSON/格式/引用/执行 | browser-export-v4.zip、verify_browser_zip.py、archive-completion-audit.log、协议校验与实际engine18例 | 完成 |
| 缺陷复现与回归 | 对应新增失败用例及逐项修复记录，workflow-ui-red.log保留前端失效复现；全量再通过 | 完成 |
| 独立复核/API/UI/build/Python3.8 | 前述独立审查记录，四份completion-audit日志均成功 | 完成 |
| 更新用户服务/原数据不变/文档与限制 | completion-runtime-proof.json、当前8001/5174服务、用户使用说明及本文明确边界 | 完成 |

证据文件位于outputs/mapping-export-deep-qa-20261028；completion-audit-manifest.json记录最终验证统计及关键源码SHA256。本次完成表示已完成所要求的审查、复现、修复与验证，不保证软件未来不再出现任何缺陷；Windows平台未实测及协议限制如前所述。
