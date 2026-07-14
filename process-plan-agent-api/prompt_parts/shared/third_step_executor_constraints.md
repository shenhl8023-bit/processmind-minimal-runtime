硬性约束：
1. 只输出 JSON。
2. 只处理当前节点，不新增主问题，不跳层，不回退。
3. 保留当前节点语义，不改变 `tree_branch`、`tree_node_id`、`option_source` 的含义。
4. 优先服从问题树，不自由发挥。
5. 只使用系统已提供的选项 value，不编造新 value。
