# 规则定稿三文件与中地 Demo 协议对齐方案

日期：2026-10-21。状态：已按授权实施；三表协议、映射身份及发布快照已接入，验收记录见 `../2026-10-21-demo-three-table-delivery.md`。真实项目未被用于测试保存或发布。

## 目标与范围

规则定稿下载的 ZIP 仅包含 `factor_table.json`、`full_route_table.json`、`rule_table.json`。文件名、顶层结构、字段、类型和引用方式遵循 `/Users/zhaoyongwei/Desktop/中地4步工艺生成Demo/结构说明.md`，具体材料、因素、工序和规则来自当前项目，不复制 Demo 的业务答案。

用户特别明确的主线是：**模板分组映射完成后产生全集路线表；规则定稿在这张表上建立启用规则。** 第三步之后的最终工序名称、工步及顺序是基准。保留部分映射，只需至少一条有效确认映射；不要求全集所有节点都映射。保持现有页面和系统风格，不增加独立“映射确认”模块。

## 实施前核实的差异

| 项目 | 实施前系统 | Demo 要求 |
| --- | --- | --- |
| 因素表 | `{schema_version, fields}`，选项为对象，source 多为来源说明 | 顶层数组；规定的六种类型；字符串选项；source 为取值路径；含 visible |
| 全集路线表 | 文件名为 full_route_structure.json；映射输出无工序、工步 ID，带技术要求和 is_last | 文件名 full_route_table.json；顶层数组；稳定 ID；不含技术要求、is_last |
| 规则表 | `{schema_version, rules, process_relations}`；含优先级与 include/exclude | 顶层数组；每个 target 最多一条 required/when 规则 |
| 路线身份 | 映射按原始工序展开，规则按归并后的工序构造 | 归并后的最终路线、映射、规则必须引用同一节点 |
| 发布版本 | 两表读发布包，路线另读当前模板映射 | 三表属于同一次发布的冻结快照 |

因此仅修改文件名，或在浏览器把对象拆成数组，都不足以保证兼容。

## 推荐做法

在后端增加统一的 Demo 协议编译和校验层，沿用现有规则分析、定稿卡片和内部 V2 数据。前端只提交定稿结果、展示现有预检结果、下载已发布快照。

备选方案有前端临时转换、全面替换内部规则模型。前者难以保证三表一致和规则语义，后者会扩大页面、存储和执行器的改动。本方案把改动集中在路线身份、协议编译、发布快照和必要的消费兼容测试。

数据流：

```text
规则分析后的最终路线
       + 已保存的模板分组映射
       ↓
映射阶段生成全集路线表（工序/工步 ID、最终名称、顺序、候选特征）
       + 规则定稿的因素、主工序与条件
       ↓
后端编译三表 → 一致性预检 → 同一次事务冻结发布
       ↓
下载三个固定名称的 JSON 文件
       ↓
下游三表引擎：CAD 取值/参数覆盖 → 选路 → 计算 is_last → 技术要求技能
```

### 1. 映射阶段产出可引用的全集路线表

工序字段顺序与 Demo 示例一致：`process_name, process_type, precision, steps, process_id`。工步字段为 `step_name, candidates, step_id`。数组顺序保留最终确认路线及其工步顺序。

```json
[
  {
    "process_name": "车削加工（A侧）",
    "process_type": "加工工序",
    "precision": "粗加工",
    "steps": [
      {
        "step_name": "车外圆",
        "candidates": {"A侧/外圆": ["外圆柱面"]},
        "step_id": "turning_a_s01"
      }
    ],
    "process_id": "turning_a"
  }
]
```

示例 ID 只说明格式；实际 ID 按节点持久身份一次分配，不依赖每次导出的名称或当前位置。改名、重排时身份不变；新增节点获得新 ID。工序和工步的 ID 在整套配置中唯一。

用归并后的最终路线节点生成工序；原始工序、工步只保留为内部来源关联。建立“原始工步 → 最终工步”身份映射，迁移现有模板映射，不依靠相同名称拼接，也不因一个最终工序有多个来源就重复输出。没有来源工序的新建节点也须进入全集。相同名称的不同清洗、检验、去毛刺节点保留不同 ID。

`process_type` 与 `precision` 分开赋值：前者为加工工序/辅助工序，后者按已确认的粗加工/半精加工/精加工或辅助工序等值输出。优先使用已有结构化阶段信息；无法确定的加工精度定位为待确认项，不用简单搜索“精”字来猜。辅助工序 `steps: []`。

只使用有效确认的映射填充 candidates，统一分组路径分隔符并去掉尾斜杠，保留协议允许的 `*` 通配符；特征名精确匹配。工序级映射若不能确定工步特征，不自动扩展成该分组下所有特征。

**部分映射的边界：** 全集保留未映射节点；明确属于通用工步的节点允许 `candidates: {}`。尚未审定候选的加工工步不能直接当通用工步自动启用：明确待核验的节点按 Demo 用 `when: false` 表示。若节点已确认启用或为主工序，则提示具体语义冲突，不能静默禁用，也不能补造候选。确认可作为通用工步的节点可继续不映射，无须补齐所有映射。

全集配置表移除 `technical_requirements`、`is_last`。这些属于生成结果。工步级证据、来源、确认状态保留在内部，不加入对外协议。

### 2. 因素表按真实数据来源导出

每个因素必须有 `key, label, type, source, visible`；按需输出 `options, required, default`，不附加内部字段。

类型映射：boolean→bool，single_select→enum，multi_select→multi_enum；string/number 保留，明确为整数的因素才用 int。选项导出为字符串数组。人工补充参数 visible=true，CAD 分组、特征与特征精度 visible=false。

建立显式因素绑定表，将当前因素 key、对外 key、类型、取值路径和选项关联起来，避免把 `CAD/PLM` 这样的说明当 source。材料等使用 Demo 已定义的 `manual_defaults.*`；CAD 特征使用 `input_json[].features[].feature_select` 等真实路径。固定 CAD 输入里不存在的尺寸、粗糙度等字段不伪造来源，可改为人工参数，通过按 key 提交的 `manual.factor_overrides` 接收值。

参数个数和选项根据项目规则生成，不固定成 Demo 的 11 个因素。因素默认值只有明确配置时才输出；不能隐含填入材料、热处理或特征需求。

### 3. 规则定稿编译成 target 规则

```json
[
  {"target": "blanking", "required": true},
  {"target": "copper_plating", "when": {"field": "surface_treatments", "op": "contains", "value": "镀铜"}},
  {"target": "copper_removal", "when": {"field": "selected_processes", "op": "contains", "value": "copper_plating"}}
]
```

target 引用全集中的 process_id 或 step_id，每个 target 最多一条规则。确认无条件保留的主工序用 required=true；有条件节点用 when；明确待核验禁用的节点可用 when=false。工步规则同样支持，不能只导出工序规则。

规则因素 key 必须来自因素表，保留系统因素 selected_processes 除外。条件使用协议允许的布尔常量、all/any/not/some 和运算符。多个因素属于同一 CAD 特征记录时使用 some，避免将一个孔的类型和另一个外圆的精度拼成同一条件；不把本来独立的人工因素强行改成 some。

现有多条规则不能直接去重或全部 OR：必须保留优先级、纳入、排除、人工开关的实际含义，生成等价的单 target 条件。contains_any/contains_all/between/not_exists 等仅在类型、空值语义一致时展开为协议支持的组合。主工序若允许人工排除，不能不经处理就改为不可排除的 required=true。

现有 requires 是“选中后补入依赖”，conflicts 是“同时选中报错”，trigger_after 还有与排除规则的冲突语义；这些不一定等价于简单的 selected_processes 条件。无法等价表达、存在同优先级相反决策或循环依赖的配置，在现有发布预检中定位到具体工序/规则，不静默丢弃、不临时交给模型猜测。order_after 等顺序约束校验最终全集的固定顺序，不把运行时拓扑排序带入 Demo。

### 4. 三表必须同一发布快照

后端发布时读取同一项目的最终路线和当前有效映射，检查路线版本、映射修订以及工作流修订，编译并校验三表后一次性保存。增加三表快照、编译器版本和来源版本/哈希；这些审计信息只在内部保存，不增加第四个外部文件，也不改变三表顶层结构。

下载只读取该发布版本的三表快照。发布后修改映射不会改变旧版本的下载内容；创建新包时使用新映射。消除前端“发布两表后另取实时映射来拼 ZIP”的窗口。

统一使用 UTF-8、中文字符直写、两空格缩进和固定字段顺序。JSON 内容为协议对应结构，项目数据不要求与 Demo 示例字节相同。

### 5. 下游消费约定

配置兼容之外，还需按 Demo 的实际消费行为验收：页面修改值 > CAD 预填 > 明确配置的 default，false、0、空数组、空字符串均不按缺失值替换。参数映射接口不要求必填已齐全；生成接口校验必填项。

非空 candidates 匹配不到实际 CAD 特征时删除工步，可选加工工序无剩余工步时删除，必选工序保留；工步仍受父工序限制。只输出 CAD 实际存在的分组/特征。

is_last 在实际过滤完成的路线中跨工序计算：一个工步只要包含一个最后加工的“分组路径+特征名”即为 true。不能沿用当前映射阶段按单个来源工序、全部特征判断的结果。技术要求仍交给既有技能，不写入三表，不从 Demo output.json 复制。

已找到并只读调用实际下游引擎：`/Users/zhaoyongwei/Desktop/KmAI-Win7-SP1-x64-20261018-r24/KmMpsMcpServer/skills/process-route-generator/scripts/config_route_engine.py`。Demo 三表和 input.json 运行后的路线与 route_output.json 的 32 道工序逐项一致；本系统编译出的材料、人工布尔开关配置也已实际运行，另验证同一特征行的 some 条件和跨工序 is_last。

本次验收覆盖三表配置、选路及候选过滤。外部 technical-requirements-generator 负责技术要求，当前系统内部 V2 生成接口并未接入该外部技能，不能把路线验收等同于完整 output.json 技术要求生成验收。

## 实施边界与顺序

1. 固定 Demo 协议与三表校验器，用样例建立格式、类型、唯一 ID、跨表引用的契约测试。
2. 统一最终路线的持久身份和来源关联；调整映射阶段的全集构建，覆盖新建节点、多个来源、重复名称与部分映射。
3. 增加后端因素、规则编译器与等价性校验；保留现有内部 V2 和定稿界面。
4. 发布接口原子保存三表快照，前端改为下载固定三表；现有预检承载具体错误提示。
5. 对照 Demo 的输入与路线标准答案，完成真实下游兼容测试，再做项目回归。

主要改动位置：

- `process-plan-agent-ui/src/composables/finalTemplateMappingOperations.ts`：最终路线与来源身份关联。
- `process-plan-agent-api/app/services/project_group_templates.py`：映射后全集路线结构。
- `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`：定稿节点身份传递，避免按名称/序号重造 ID。
- `process-plan-agent-api/app/services/rule_packages/`：协议模型、因素/规则编译、引用/依赖校验与发布快照。
- `process-plan-agent-api/app/models/models.py` 及数据库维护逻辑：保存三表和来源版本。
- `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`：下载已发布快照，固定文件名。

大模型可继续参与前面的规则解释或建议；**这一步最终 JSON 由确定性程序编译、校验和导出**，不新增一次让模型自由拼三表的请求。

## 验收标准

1. ZIP 恰有三个固定文件；三表均为数组，字段、枚举类型、选项、取值路径、空值和编码符合协议，没有 V2 包装及额外内部字段。
2. 所有 ID 唯一，target 引用存在；改名和重排不改变节点身份，多来源归并不复制工序，重复名称节点不丢失，新建节点正常导出。
3. 映射后的全集节点和顺序完整保留；部分映射合法；通用和待核验工步处理明确，未映射不自动等于通用。
4. 同特征条件不跨行匹配；优先级、纳入/排除、人工开关及依赖关系转换前后等价；无法表达的配置明确报错。
5. 依赖支持前向引用，未知引用、循环和重复 target 报错；输出顺序始终来自全集。当前项目确认的末尾“清洗→检验→包装”保持一致。
6. 三表来自同一发布；修改映射后重新下载旧版本，三个文件内容不变。导出失败不留下半套已发布三表。
7. Demo 自带三表加 input.json 在真实下游引擎产生与 route_output.json 一致的 32 道路线，证明基线；本系统编译的独立配置在同一引擎中验证材料来源、人工 true/false 覆盖和候选过滤。32 道是 Demo 样例的预期值，不写死到系统，也不要求其他项目有相同数据。
8. 生成后的 is_last、同特征行条件及候选过滤分别验证。外部技术要求填充属于后续集成边界；不能用配置表或标准答案复制来冒充生成。
