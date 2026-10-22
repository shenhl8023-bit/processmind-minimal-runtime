# Demo 三表实施与验收

执行已授权设计 `../specs/2026-10-21-demo-three-table-export-design.md`。

- [x] 修复映射树：每个最终路线节点对应一个父工序；与第三步共用工步构造，保留真实来源引用；新增、同名、合并及拆分节点均不丢失。
- [x] 映射保存：最终工序/工步稳定 ID 生成 Demo 全集；支持部分映射；过滤失效来源。
- [x] 后端确定性协议编译；无法等价表达的内部规则由现有预检定位。
- [x] 同一事务冻结三表及来源版本；ZIP 只读发布快照。
- [x] 完整 UI/后端回归及构建；真实下游引擎 Demo 验收；浏览器核对当前树，不用真实用户项目测试发布。

验收：后端 578 passed / 9 skipped；前端 251 passed，生产构建成功；实际下游引擎 4 项测试执行通过。详细边界与操作见 `../2026-10-21-demo-three-table-delivery.md`。

分工：根线程负责前端及集成；mapping_route_backend 负责映射后端；demo_table_compiler 负责协议编译；three_table_publication 负责冻结发布。
