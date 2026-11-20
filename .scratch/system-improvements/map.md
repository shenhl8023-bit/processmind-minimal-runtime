# 系统改进总账

创建日期：2026-11-03（北京时间）

最近更新：2026-11-20

当前交付完成（2026-11-20）：[PM-093](issues/93-full-release-git-20261120.md)已提交并推送产品版本2044465到origin/codex/zhaoyw；交付`dist-win7/processmind-win7-full-template-20261120-pm092.zip`，46,434,947字节/2277文件，full且包含PM-091及PM-092/038。ZIP/逐文件摘要/Win7运行时/解压API启动通过；前后端全量及构建通过。正式数据/设置保留，PM-065继续deferred；Win7实机尚未测。详见[交付验收](../../docs/superpowers/reviews/2026-11-20-full-release-acceptance.md)。
联合修复完成（2026-11-20）：PM-092与PM-038已修正响应分类/有限空正文恢复及问答就绪保存时序，并通过真实连接、34工序生成、第四步/第五步联动。后端2294 passed/111 skipped、前端1418 passed/1 skipped、构建、Python3.8静态语法与独立复核通过。仍有外部请求偶发超时，非性能保证。正式数据库/设置SHA-256未变，最新8000/5173已启动；PM-091改动保留，未打包、提交或推送。见[联合验收](../../docs/superpowers/reviews/2026-11-20-model-response-repair-acceptance.md)。
未实施项盘点（2026-11-20，交付后）：93张工单中92项done，仅PM-065（28份同等样本分支全集方案）仍needs-info/deferred。PM-038本轮真实第三步生成已验收；PM-089经完整包及Git提交d459731核对补记关闭，PM-091后续修复已随2044465提交推送。
PM-065口径已更正：用户确认28份PDF同等参与，联合生成允许分支的全集，替代“8份定基准、20份补充”的建议；具体归并与规则尚待讨论。见[PM-065](issues/65-eight-typical-route-benchmarks.md)。
PM-065讨论28份PDF如何接入现有上传、归并、规则和验证步骤，记录材料角色、分支回放与三表兼容边界；未实施。见[PM-065](issues/65-eight-typical-route-benchmarks.md)。
PM-065已交付八类分叉全集工作簿：64段、八类样本的255次原工序及前后段已回读核对。见[PM-065](issues/65-eight-typical-route-benchmarks.md)，产品实施仍延后。
PM-065主线加分支讨论（2026-11-20）：核对八类共有的四个阶段与分支还原结果，记录展示或生成两个适用范围，方案未定。见[PM-065](issues/65-eight-typical-route-benchmarks.md)。
第三步新反馈排查（2026-11-18）：[PM-092](issues/92-step3-invalid-model-response-diagnosis.md)用户已确认发生在本机；项目10问答生成90.31秒后503，响应正文无法提取；“接口不兼容”为通用提示，尚不能定为协议问题。另一个必答提醒是前端确认草稿校验，两条通知汇总显示。当前日志缺少返回结构，已记录诊断边界；只读核对及离线分类验证，无产品/数据/设置改动。
PM-065参考表车削分段复核（2026-11-18）：首轮与再次车削分列；两处后续车削可在全集中提前展示且八类原序不变。见[PM-065](issues/65-eight-typical-route-benchmarks.md)，仍为审阅建议。
PM-065连续工序段复核（2026-11-18）：[64行连续对照](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类全集工序段再合并_候选对照.md)按单类连续段及分支对齐展示；65行整块版、64行拆分024的S4分支版和61行概览版都已与八类255次原ID逐项核对。64块替代89块作为助手的客户审阅建议，非执行规则。见[PM-065](issues/65-eight-typical-route-benchmarks.md)，V3未改，Execution仍deferred。
导出兼容修复完成（2026-11-18）：[PM-091](issues/91-conditional-required-export-compatibility.md)按用户确认保留特征选择/校验与三个JSON文件，补齐required_when及本机KmAI读取器；修复导出误报、陈旧响应和有效必填判断。前端1416、后端2262通过，浏览器真实下载及21次缺项检查通过，两组30/31工序与原生一致。已生成full完整修复包并附接收端更新说明；另一电脑/Win7实机待复测，正式数据/配置保留，未新增Git提交或推送。
PM-065 V3再合并复核（2026-11-18）：同阶段同任务键25对中2对可直接归块；再按5组有共同目的的任务归块，形成89块审阅候选。八类255次原ID及顺序逐项还原，保留不同位置的重复加工；具体决定、86块备选及复核证据见[PM-065](issues/65-eight-typical-route-benchmarks.md)。仅为分析，V3及产品未改，Execution仍deferred。
PM-065工序块合并版V3交付（2026-11-18）：按用户授权借鉴“连续全集→工序块→块内节点”，将194个显示项整理为[96块连续Word审阅稿](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类典型工艺连续全集路线_工序块合并版V3.docx)，共7页，001下料与备料至096防护包装。255次原ID唯一归属，八类次数/原顺序展开一致、块图无环；最终分页及中文逐页检查通过。96为组织块数，块内原方法、对象、次数、阶段、按需/虚拟及来源保留；只覆盖八类，原20份尚未并入。分块为助手审阅决定，原稿与产品保持，Execution仍deferred，详见[PM-065](issues/65-eight-typical-route-benchmarks.md)。
PM-065外部超集片段表分析（2026-11-18）：按用户限定仅分析“片段名称”“节点片段”两列，确认53片段容纳89个唯一节点ID，含10个多节点块及43个单节点片段。前段A/B及周边加工块体现块内保留方法、对象、方位的结构；重复基准修研、清洗检验仍保留阶段位置。建议借鉴层级继续整理194项，未生成新稿或修改系统；两列缺少前面八类的8种显式方法，完整覆盖与装夹兼容性待核定。详见[PM-065](issues/65-eight-typical-route-benchmarks.md)及[结构分析](evidence/pm-065-route-differences/workbook-fragment-review-20261118/analysis.md)，Execution仍deferred。
PM-065相似工序整理版V2交付（2026-11-18）：按用户要求将198项整理为[194项连续Word审阅稿](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类典型工艺连续全集路线_相似工序整理版V2.docx)，共8页。合并淬火前车外圆/车槽、末道防护包装及整理后相邻去毛刺，统一钻镗/钻铰/研顶尖孔名称并标明阶段和×2次数。255次来源按ID展开后八类次数/顺序一致，最终逐页渲染正常；194为显示项，工步参数与内部出现位继续保留。旧稿保留，原20份未并入；仅文档整理，产品Execution仍deferred。详见[PM-065](issues/65-eight-typical-route-benchmarks.md)。
PM-065相似工序继续归并评估（2026-11-18）：新增[198项合并建议](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/198项全集相似工序合并建议_20261118.md)，较强候选为018/026车外圆车槽及196—198防护包装；在原240节点图追加两组候选后，无环且八类255来源ID顺序/次数还原。名称归一与车削收为工步另列待核定，不猜新总数；仅建议，原Word及产品未改，Execution仍deferred。
发包复审已完成（2026-11-17实施，2026-11-20核对记录）：[PM-089](issues/89-release-review-full-package-git.md)已有full完整包20261117-r4及验证记录，本地Git提交d459731已完成，原in-progress状态已纠正。保留正式数据/配置与PM-065 deferred；后续PM-091改动尚未追加提交。
PM-065 198项连续全集Word交付（2026-11-17）：按对话结果生成[8页Word审阅稿](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类典型工艺连续全集路线_198项合并审阅稿.docx)，001—198一张连续表，含类别说明及合并范围；结构核对与最终8页中文渲染检查通过。仅文档交付，原20份未并入，PM-065产品Execution仍deferred。
PM-065单条全集展示澄清与核验（2026-11-17）：按用户要求展示一条连续全集，纠正此前共享段＋八条路线的答复。240行先合并相邻同名为202行，再合并两处二项紧接重复段为[198行审阅稿](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类连续全集路线_显示合并198行.md)；未发现三项及以上紧接重复段。255次来源/240原行完整保存在JSON，仅显示压缩，未验证压缩后逐类执行回放，未并入原20份或修改产品，PM-065 Execution仍deferred。
PM-065连续全集修订（2026-11-17）：用户明确要从下料排到末道的一条全集，已按此生成[连续路线V2](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类典型工艺连续全集路线V2.docx)，一张表001下料/备料至240油封包装，11页；八类交叉排列、阶段作行内注，次数及原顺序验证一致。沿用九组共享候选，未新增合并或并入原20份；[PM-065](issues/65-eight-typical-route-benchmarks.md)已记录本次澄清，产品Execution仍deferred。
PM-065重复工序公用分析（2026-11-17）：用户继续指出连续全集中有大量重复工序，已对255次原出现和240个首轮候选节点扫描，发现33组跨路线同名工序、210次出现。新增[公用分析V1](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类重复工序公用分析V1.md)和[共享决策矩阵](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类重复工序共享决策矩阵.json)：首轮9组已共享，另列1组直接共享候选、17组模板复用并保留出现位、6组待核定。未改正式母路线、产品或规则包，PM-065仍needs-info、Execution仍deferred。
PM-065连续同名显示去重（2026-11-17）：用户要求先合并连续相同的工序名称。本轮将连续全集240个显示节点按相邻同名压缩为202组，减少38行；油封5组、末段清洗8组、末段检验8组及包装2组分别合并显示，保留路线归属和同一路线重复次数。仅改变审阅显示，不改变原路线身份、顺序或正式数据；前段可补A侧加工阶段标签，但不以A侧替代车削、钻镗、铣削等具体工序。
PM-065重复连续段合并（2026-11-17）：用户要求进一步合并连续重复模式，例如A-B-A-B及连续三项以上。本轮基于8条独立路线提取23个连续公共子链，最长为N2/N4的`研孔→研孔→清洗→检验→油封`、N1/N2的`车外形→车外形→去毛刺→清洗→检验`、S1/S3/N4的`钻孔→去毛刺→清洗→检验`、S2/S4的`珩孔→研孔→清洗→检验`。建议以共享段定义＋路线段序列表达，路线内重复段保留×2；仅为分析显示建议，未改正式母路线、产品或规则包。
当前全系统审查完成（2026-11-17）：[PM-082](issues/82-system-defect-audit-20261117.md)及PM-083～088六项缺陷均已修复、回归和独立复核。前端1396 passed/1 skipped、后端2175 passed/111 skipped，构建、Python3.8语法及diff检查通过。第二步空结果/重试、第五步参数变化及迟到响应、共享Ra导出和取消清理均有真实回归。正式8000已安全重载，项目9/20份PDF/规则/模型配置保留，仅启动审计时间更新；5173保持。见[验收报告](../../docs/superpowers/reviews/2026-11-17-system-defect-audit.md)。Win7实机及真实模型端到端未测，PM-065产品仍deferred。
当前界面批次完成（2026-11-17）：PM-072～081及PM-067同类问题跟进已实现并验证。第三/四步筛选位置样式一致，判定区约缩短54%并统一系统蓝色；问答数字28px、规则同排30px，窄规则面板的范围数字完整显示；第五步两列输入/工步默认收起、第四步展示精简和隐藏映射提示均完成。最终前端1383通过/1跳过、93文件通过/1跳过，TypeScript/Chrome109构建及浏览器交互通过。见[本批验收](../../docs/superpowers/reviews/2026-11-17-compact-workflow-acceptance.md)。正式项目9与8000/5173服务保留，Win7实机未测；下方讨论/deferred文字为历史，以当前索引及工单Answer为准，其它deferred工单不在本批范围。
追加并执行PM-081（2026-11-17）：用户要求继续收紧第三步判定区域并更换淡绿色背景；已记录[工单](issues/81-compact-analysis-judgment-panel.md)，按系统蓝灰tokens、扁平条件标签、合并标题和操作布局实施。第三/四步筛选位置比较：助手建议继续放在工序树标题栏右侧，作用范围清晰，沿用用户此前已确认位置与一致样式。
PM-065文档交付（2026-11-17）：按用户要求生成[八类全集路线Word审阅稿V1](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类典型工艺全集路线审阅稿V1.docx)，31页，含共享骨架、240节点完整目录、八类展开和条件依据。255次来源覆盖、244条顺序约束及八类原序列投影检查通过，完成最终逐页渲染检查；仅合并九组候选，原20份尚未并入，非最终节点数。详见[PM-065](issues/65-eight-typical-route-benchmarks.md)，未改产品及正式数据，Execution仍deferred。
第三步追加精简（2026-11-17）：用户确认执行[PM-079](issues/79-simplify-analysis-review-filters.md)只保留全部/待处理筛选（待处理含原待确认与确认中）、[PM-080](issues/80-compact-analysis-operation-header.md)当前工序头部仅保留名称/状态/位置/导航，移除重复统计与分类标签；并入当前收尾，不改变规则与问答保存。
本轮追加授权（2026-11-17）：用户确认移除PM-076“查看判定依据”，要求本轮全部问题修复；新增并执行[PM-077](issues/77-align-validation-input-panel-style.md)第五步只统一左侧输入区（右侧样式不改）、[PM-078](issues/78-hide-mapping-reset-dialog-copy.md)隐藏映射后第二/三步重新生成提示不提第六步，并同步核对第四步同类提示。PM-072～078为当前范围，不扩大其它deferred工单。
PM-065合并方案及首轮验证（2026-11-17）：助手推荐一套母路线按族/阶段复用兼容节点，其余独立。255次原工序仅合并九组候选后为240个分析节点，全目录顺序无环，8类原ID序列投影逐项一致；仅验证顺序，未核定全工步、未含原20份、非最终节点数。见[结果](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/九组共享候选保序验证.json)与[PM-065](issues/65-eight-typical-route-benchmarks.md)。保留旧工步/身份及顺序、逐段增加共享，再接条件；方案待确认，产品Execution仍deferred。
第五步紧凑化（2026-11-17）：新增并执行[PM-072](issues/72-default-collapse-generated-process-steps.md)工步默认收起、[PM-073](issues/73-two-column-feature-inputs.md)同类特征两列布局。用户追加询问第四步“修改原始描述／重新识别”的用途，正在核对；不触发正式项目重新识别或保存。
第四步更多操作评估（2026-11-17）：[PM-074](issues/74-review-finalize-more-actions.md)核实两个按钮仍有实际调用；助手建议移除常规菜单入口、保留异常重试识别。尚未视为用户确认删除，产品变更deferred。
追加确认与讨论（2026-11-17）：PM-074用户已确认移除两个常规入口、保留异常重试；新增并执行[PM-075](issues/75-remove-validation-precision-rule-hints.md)移除第五步重复精度阈值说明。新增[PM-076](issues/76-review-finalize-evidence-display.md)评估第四步“查看判定依据”，仅建议移除展示，尚未获确认。
PM-060配置应用（2026-11-17）：用户要求加入隐藏开关配置，根目录新增 `product-features.json` 并设 `template_mapping_enabled: false`；已重启本地后端，直连及前端代理接口返回关闭，Chrome 页面导航仅显示第一至第五步。详见[PM-060](issues/60-configurable-template-mapping-visibility.md)。
PM-065资料合并用途说明（2026-11-17）：PDF提供原工序/工步及顺序，DOCX补充目的、阶段和可选依据；助手建议据此制作带来源的共享/独立、路线归属、出现条件与先后关系对照，构建全集保留可选节点，具体生成再筛选。三因素分类保持，新增结构/配套依据不自动变为全局必填。详见[PM-065讨论记录](issues/65-eight-typical-route-benchmarks.md)，本轮未改产品，Execution仍deferred。
本轮交付完成（2026-11-17）：PM-059剩余复用、PM-066～070及追加PM-071已实现并验证，前批PM-060～064同步关闭。真实隔离项目41工序采纳、32条件一次确认保存，冷刷新第五步使用同版规则生成31步；前端1375全量及构建通过，后端2160全量通过，最后来源memo后57相关回归和81共享投影回归通过。独立审查4项问题均修复；详情见[验收报告](../../docs/superpowers/reviews/2026-11-17-workflow-polish-acceptance.md)。下方deferred与待讨论为历史，当前索引/工单Answer为准；PM-065产品实施仍deferred。
新增并授权PM-071（2026-11-17）：用户要求本轮完成后精简规则问答页，删除截图中的同现/缺失工序统计、原文件称呼、内容证据摘录及“已保存判定结论”展示。按[PM-071](issues/71-simplify-analysis-question-workspace.md)先收尾PM-066～070关键链路，再移除这些展示并回归，问答/保存数据与其它样本文档入口保留。
PM-065 DOCX补充核对（2026-11-17）：8份正式说明为7类单件＋1份组件，7个典型件号与PDF一致；后加2份均为162字节Word锁文件，S4氮化氰化衬套正式说明仍缺。新增15组安排依据及来源差异，不变更已确认三因素分类或擅自增加必填项。见[对应与条件报告](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/DOCX与八类PDF对应及共享条件补充.md)及[PM-065](issues/65-eight-typical-route-benchmarks.md)。仅分析记录，Execution仍deferred。
PM-065共享分析建议（2026-11-17）：区分共用工序模板与合成同一节点，列九组优先共享候选及阶段/对象不同应独立的实例；要求参数分别保留、次数与顺序可还原。[判断表](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类路线共享与独立判断.md)与[工单](issues/65-eight-typical-route-benchmarks.md)已更新，属于助手建议，尚非逐节点裁定或用户确认；未生成共享图、未改产品及正式数据，Execution仍deferred。
PM-065分析顺序确认（2026-11-17）：用户要求先生成八类独立路线，再分析如何合并。已还原8条工序级原文路线，S1/S2/S3/S4/N1/N2/N3/N4为29/39/39/44/26/26/31/21节点，共255个（目录254＋额外虚拟卡1）；原编号、重复阶段、按需/虚拟、来源页码及目录/卡片分歧保留，源文件哈希与序列核验通过。见[独立路线总览](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/八类独立路线_20261117/八类独立路线总览.md)及[PM-065](issues/65-eight-typical-route-benchmarks.md)。本条更新上一轮助手先联合生成再核验的推进建议；上传仍为可用数据入口，但当前先以8条为基准分析共享/独立。未改正式数据或产品，Execution仍deferred。
PM-065全集扩充路径澄清（2026-11-17）：用户指出将8份典型补充上传即可获得全集。已核对现有同项目上传→提取→全集生成/归并调用链，确认可优先用28份共同生成新全集候选，再按差异表检查完整性、重复阶段与顺序；旧20份的8种缺失方法可由新资料提取补入，不要求先手工建工序或开发另一套全集生成器。尚未实际上传/生成28份结果，不预判阶段问题自动解决或流程必然失败。[PM-065](issues/65-eight-typical-route-benchmarks.md)已更新；本轮仅讨论，正式数据未改，产品Execution仍deferred。
新批次已获实施授权（2026-11-16）：用户设置明确目标，要求实现以上需求、发现缺陷及时修复并打开系统测试。PM-066～070及PM-059剩余通用对象复用现启动，替代下方先记录/deferred的历史状态。按[实施计划](../../docs/superpowers/plans/2026-11-16-workflow-polish.md)先规则/推荐贯通、并行界面与闪烁修复，再第三至第五步整链验证及回归。正式数据/模型设置保留，无提交、打包或发布。进度见[执行记录](evidence/pm-066-070/progress.md)。
第三至第五步贯通为硬性验收（2026-11-16）：用户要求第三步推荐可一键采纳、第四步规则条件可一键确认，并补充“而且可以正常到第5步”。已纳入[PM-070](issues/70-complete-finishing-recommendation-chain.md)及[PM-069](issues/69-finishing-object-before-precision-basis.md)：用整条路线实际验证采纳→确认并保存→刷新→第五步加载最新规则和因素→填写实际参数后生成，复用对象、独立阈值和来源校验贯通，不以按钮显示/路由跳转或单道样例替代。真实缺项明确定位，正常完整路线不应因内部衔接被阻止。两项Execution仍deferred，未声称已修复。
对象复用原则已澄清（2026-11-16）：用户强调磨孔→珩孔只是举例，要求举一反三。[PM-069](issues/69-finishing-object-before-precision-basis.md)及[PM-070](issues/70-complete-finishing-recommendation-chain.md)统一为后续加工先复用已确认的同一具体特征/适用方位，只问缺项和本工序新增条件；各工序精度阈值独立，一键推荐同样复用。此前助手“每道精加工完整四题／每条推荐重复全套字段”的解读撤回，仅缺项时按特征→方位→类型→阈值补问；不得硬编码示例工序对。两项仍ready-for-agent、Execution: deferred。
新增推荐贯通需求（2026-11-16）：[PM-070](issues/70-complete-finishing-recommendation-chain.md)记录一键推荐在精加工被阻止。隔离真实函数复现缺方位时磨外圆/磨端面停住，后端仍接受仅阈值推荐；助手建议完整对象/方位/类型/阈值统一生成校验、旧未完成项按可靠参考补齐、单项缺失不阻断其它工序。与PM-069联合处理，ready-for-agent、Execution: deferred，未修改正式推荐数据，未冒称已核定全部现场工序缺项。
精加工提问顺序已确认（2026-11-16）：用户回复“同意这样”，[PM-069](issues/69-finishing-object-before-precision-basis.md)按特征→方位→精度类型IT/Ra→阈值定稿，替代此前助手提案待确认状态。ready-for-agent、Execution: deferred，纳入下一批；与PM-059阈值后置保持一致，并进一步把类型选择也后置。
新增下一批记录（2026-11-16）：[PM-066](issues/66-align-analysis-finalize-operation-trees.md)第三、第四步左侧工序树及第五步右侧路线生成结果参照第二步统一紧凑展示；[PM-067](issues/67-unify-numeric-threshold-controls.md)统一所有阈值控件的大小、字号、间距及按钮样式，用户明确不限于精度阈值；[PM-068](issues/68-finalize-unsaved-indicator-and-entry-flicker.md)调整第四步“未保存”提示并复现排查进入页面闪烁。三项先记录、Execution: deferred；闪烁尚未复现或确定根因，正在收尾的PM-059～064授权范围不变。
PM-065实证差异对照（2026-11-16）：已按用户要求完成当前41节点/439明细与八类255条典型工序对照，20份上传PDF与JRT原件SHA256全部一致；178条同名、61条同义/复合候选（未核定复用），11条涉及8种未见方法，5条需扩充对象/工步，另列11个顺序反例。原20份无普通铜合金活门/衬套样本。见[差异报告](twenty-vs-eight-route-differences-20261116.md)、[工作簿](../../outputs/01a1e324-2ac9-7aa1-b750-825db0e99128/二十份全集与八类典型路线差异表.xlsx)和[PM-065](issues/65-eight-typical-route-benchmarks.md)。后续建议先做新旧身份映射及阶段拆分再接两层条件，未改产品或正式数据，产品Execution: deferred；下方“未完成比对”为此前历史状态。
PM-065现有全集覆盖缺口（2026-11-16）：用户指出原二十份全集缺少八份典型中的工序。已将下一步建议收敛为二十八份及现有全集联合对照、形成扩充版全集，补工序/工步/阶段并保留可复用身份，随后设置路线归属和局部条件；缺失清单尚未实际核定。前轮“无须重传”只指本地读取方式，不代表旧全集足够。[PM-065](issues/65-eight-typical-route-benchmarks.md)及[分析报告](eight-typical-routes-analysis-20261116.md)已同步，Execution: deferred，未重导入或修改产品。
PM-065全集资料范围澄清（2026-11-16）：用户提出八类全集如何融入系统，随后先询问是否须与原二十份一起上传。已确认本地指定目录含八份典型和二十份JRT PDF，可直接读，无须为本聊天重传；八类骨架可先单独分析，最终若要覆盖原二十份则需联合对照，尚未完成二十八份联合分析或逐份身份比对。已记录现有固定母路线筛选、工序/工步身份和全目录排序的机制与限制，详见[PM-065](issues/65-eight-typical-route-benchmarks.md)。资料角色分工及融合方案仍为助手建议，未导入正式数据，Execution: deferred。
PM-065两层判定已确认（2026-11-16）：用户明确材料大类＋零件类型＋特殊处理check先确定八类中的路线，再由具体特征＋对应方位＋所需精度判断其中条件加工工序是否出现。替代此前类内因素层级仅为建议的状态；与PM-059/063同对象参数匹配及单组输入衔接，固定/人工/关联等既有工序安排方式保留，详细阈值和处理链继续核定。[PM-065](issues/65-eight-typical-route-benchmarks.md)及[分析报告](eight-typical-routes-analysis-20261116.md)已同步，Execution: deferred，不扩展其它批次实施范围。
PM-065特殊处理check语义已确认（2026-11-16）：用户明确处理要求为勾选项，全部不勾选即普通组，勾选即对应特殊组；分类标识为氮化/氰化、硬质阳极化，分别结合钢件/有色金属，再按活门/衬套分八类。普通组不额外要求选择或确认；替代下方旧“输入枚举及未勾选归属未确认”状态。实际处理名称仍完整保留，材料适用边界、执行链及动态显示细节继续核定。[PM-065](issues/65-eight-typical-route-benchmarks.md)和[分析报告](eight-typical-routes-analysis-20261116.md)已同步，Execution: deferred。
PM-065处理分组数量澄清（2026-11-16）：用户追问处理要求是否只有两个。已解释钢件为普通/氮化氰化两组，有色金属为普通/硬阳化两组，四组各分活门/衬套才是八类；实际处理名称不止两种，普通样本仍有调质、淬火、镀铬等，不能据分组数压缩处理词表。沿用[PM-065](issues/65-eight-typical-route-benchmarks.md)，具体适用边界仍待核定，Execution: deferred。
PM-065铜合金牌号网上核对（2026-11-16）：依用户要求查询，官方标准平台国家标准项目说明及中国机械工程学会期刊平台原始研究论文互证标准写法QAl10-4-4（小写字母l），类别为铝青铜/铜合金/有色金属。此前“标准写法待核定”由本条替代；结合源文件相同后缀及材料标准，建议对本批QAL 10-4-4／QA110-4-4归一化并保留原文，来源及推断边界见[PM-065](issues/65-eight-typical-route-benchmarks.md)。[分析报告](eight-typical-routes-analysis-20261116.md)已同步，未扩大为处理路线规则批准，Execution: deferred。
PM-065材料整理顺序讨论（2026-11-16）：用户追问是否先提取全部材料再分类。助手建议复用八份资料现有提取结果，按业务范围整理原始牌号及来源、核对去重，再建立牌号→子类→大类映射，后续按需扩充；材料大类与活门/衬套类型分别判断，不以材料清单穷举或现有三个界面候选代替八类判定。详见[PM-065](issues/65-eight-typical-route-benchmarks.md)，建议未视为新实现授权，Execution: deferred。
PM-065基本因素已确认（2026-11-16）：用户明确总结“材料大类＋零件类型＋处理要求”对应八类，三维基本分类框架由候选转为已确认，替代下方旧待确认状态。具体牌号保留，普通组等正向边界及具体映射/处理规则继续核定；不扩大为完整选型规则批准或实施授权。[PM-065](issues/65-eight-typical-route-benchmarks.md)及[分析报告](eight-typical-routes-analysis-20261116.md)已同步，Status: needs-info、Execution: deferred。
PM-065关键工序识别（2026-11-16）：针对用户“氮化／氰化组有什么特殊工序标识”的批注，已核对两份最直接标识均为渗氮（活门100、衬套125）；镀铜保护、局部去铜加工、渗后除铜为样本配套线索，不能单靠镀铜、材料或通用“特殊过程”标签归类。现有正文无独立氰化，生成输入须有明确处理依据，详见[PM-065](issues/65-eight-typical-route-benchmarks.md)，仅讨论，Execution: deferred。
PM-065八类对应表（2026-11-16）：按用户追问，已在[分析报告第二节](eight-typical-routes-analysis-20261116.md)展开材料大类×零件类型×处理分组到八类的样本对应，附代表材料及6061衬套硬阳化候选示例。普通组正向边界及氰化复用范围仍待核定，处理未知不自动归类；未将解释视为自动规则确认或实施授权，[PM-065](issues/65-eight-typical-route-benchmarks.md)仍needs-info、Execution: deferred。
PM-065材料层级讨论（2026-11-16）：用户追问分类是否应提取钢件/有色金属等大类。已澄清材料类别用于首层分流，助手建议同时保留子类与具体牌号，当前有色金属样本还需区分铝合金/铜合金；牌号到类别可按核定映射派生，不只凭大类决定处理路线。未将问句视为删除牌号或新界面确认，详见[PM-065](issues/65-eight-typical-route-benchmarks.md)，needs-info、Execution: deferred。
PM-065材料核对（2026-11-16）：用户询问截图是否只有三种材料。当前默认候选确为9Cr18、4Cr14Ni14W2Mo、6061，界面依当前规则包选项显示；八类资料另有铜合金牌号（原文QAL 10-4-4／QA110-4-4，统一写法待核定），不能据三项推断八类材料已完整覆盖。仅更新[PM-065](issues/65-eight-typical-route-benchmarks.md)，未新增产品材料候选，Execution仍deferred。
当前实施（2026-11-16）：用户已明确启动PM-059／060／061／062／063／064（人工安排）这六项，替代此前deferred。按[开发范围与顺序](../../docs/superpowers/specs/2026-11-16-feature-inputs-scope-design.md)及[实施计划](../../docs/superpowers/plans/2026-11-16-feature-inputs-development.md)推进：先PM-059／063规则与共享输入，再PM-064／062第五步收尾，PM-061独立布局、PM-060配置导航并行处理，最后联合验证。六类分类作为助手的显示组织决定记录，不冒记用户逐项确认。正式数据、设置及既有工作区保留；无提交、打包或发布。当前同号“八类典型路线”资料分析工单仍未收敛，不纳入本次产品实施。实际进度见[执行记录](evidence/pm-059-064/progress.md)。
PM-065最新讨论（2026-11-16）：用户提出先识别能判定八类典型路线归属的影响因素。助手候选为零件结构/功能类型、材料及关键表面处理要求，区分类别因素与类内工序因素，未知不默认普通组，材料不能单独推出处理。具体分类取值/规则待核定，needs-info、Execution: deferred；详见[PM-065](issues/65-eight-typical-route-benchmarks.md)。路线分析原编号与人工安排PM-064重号，现统一为PM-065并保留旧证据路径；人工安排工单及既有决定不变。
新增讨论PM-065（2026-11-16）：用户反馈客户希望路线生成满足圈出的八类典型工艺，已完成八份PDF、334物理页的资料分析，综合目录经换行/连写复核共254个编号。关键差异为处理体系、加工阶段、同名工序对象及辅助链；源文件按需/虚拟和目录卡片分歧单独保留。[PM-065](issues/65-eight-typical-route-benchmarks.md)为needs-info、Execution: deferred，详见[分析报告](eight-typical-routes-analysis-20261116.md)。八份作为强制标准还是典型骨架、验收粒度及具体方案待核定；未复现具体生成错误，不把八套母路线或统一阈值记为已确认。下列“还需讨论1项”是新增本项之前针对PM-059～PM-063的历史统计，本项另列待收敛，既有决定及实施授权不变。
PM-064最新补充：用户明确第五步人工安排复选框一行可以放2或3项，替代此前助手的一项一行示意。每项仅复选框＋名称，去掉单项卡片、来源／类型／默认否标签、完成图标和逐项重复说明；助手建议按输入面板宽度自适应3／2／1列，长名称完整可辨。已核对默认false有效语义并归档原图，详见[PM-064](issues/64-compact-manual-process-checkboxes.md)，ready-for-agent、Execution: deferred。仅记录，不扩展到其它布尔条件。当前为PM-059／060／061／062／064共5项待统一实施；PM-063六类归组提案仍待确认、PM-038仍待生成验证。
PM-063最新分类提案：用户询问将其余项放“其他特征”是否合适。助手建议六个显示分类：外圆、平面、孔、槽、倒角／倒圆、其他；其他中逐项保留内螺纹、外螺纹、锥面、球面，当前31个名称全部覆盖。仅按已选特征整理第五步显示，不改变第三步候选映射或具体特征身份，完整表见[PM-063](issues/63-feature-based-route-validation-inputs.md)。分类明细和空分类隐藏待确认，needs-info、Execution: deferred，仅记录。
最新确认及剩余讨论统计（2026-11-16）：用户对特征输入展开示意回复“可以这样”，确认每种具体特征一组方位／所需IT或Ra、勾选后原位展开、取消收起，本期不加同种特征多组。PM-059实际输入范围随之收敛，转ready-for-agent。当前还需讨论1项：PM-063完整特征类别及具体归属；PM-059／060／061／062共4项已具备实施条件、Execution均deferred。PM-038另为第三步实际生成待验证，不计为未讨论需求。技术绑定、进度及保存细节留待设计，不另扩大为用户必答业务问题。
PM-063展开样式前轮提案（已由上条确认）：用户要求查看具体样式，助手提供独立可点击示意，建议勾选特征后在其下方原位展开方位和所需实际IT／Ra，取消勾选收起，不加同种特征多组入口。主要展开／收起及分项参数交互已检查，详见[PM-063](issues/63-feature-based-route-validation-inputs.md)，未改产品功能。
PM-063／PM-059最新范围：用户明确同一种通孔需要按不同方位／精度添加多组的场景暂不会出现，本期不增加“添加一组”入口，也不作为必须讨论的前置问题。助手将方案简化为每种具体特征各自一组方位及所需IT／Ra，不同特征分别填写；具体规则绑定与分类细节继续讨论。两项保持needs-info、Execution: deferred，仅更新记录。
PM-063／PM-059前轮讨论（多组入口已由上条替代）：用户指出各特征的方位和精度可能不同。助手曾建议类别内每个实际特征独立保存方位及所需IT／Ra，勾选后默认一组，同类特征有差异时“添加一组”；规则必须在同一组内同时匹配，避免跨对象拼接。多组建议保留为历史，不列入本期范围。
PM-063最新确认：第五步各特征类别只展示第三步用户已勾选、并以第四步当前保存结果为准的具体特征。孔类只选通孔／盲孔就只展示这两项，外圆类、槽类同样处理；不直接展开完整候选字典，也不默认勾选新零件的全部展示项。对象绑定、层级及实际精度输入粒度仍待收敛，needs-info、Execution: deferred，详见[PM-063](issues/63-feature-based-route-validation-inputs.md)。
PM-063现状盘点：按用户要求只读核对当前任务“123”的配置（id=8、revision=3），现有15个特征映射分组、31项去重特征，与默认字典一致；尚无独立的平面类／孔类统一几何分类。已核对三元组v3.7第十四节：具体特征名称属于C01a候选值，现有映射分组用于筛选候选；方位／IT／Ra是独立条件。完整现状表及说明已记入原工单，仅解释当前词表，不确认新分类或变更执行授权。
PM-063新增：用户指出第五步加工因素按钻孔、铣扁等工序分组导致重复，希望从第三步汇总平面类／孔类等具体特征及方位、精度。已核对当前字段与分组均按工序作用域，孔候选还混合上下位类别和表面属性；助手建议按对象共享输入并整理分类，具体粒度待确认。详见[PM-063](issues/63-feature-based-route-validation-inputs.md)，needs-info、Execution: deferred；关联PM-059已定精加工对象确认流程，截图已归档。
PM-059最新确认：用户明确“可以按照这种方式”，确认按精度／粗糙度触发的精加工先确认加工特征与方位（单选），再设置IT／Ra规则阈值；已有确认信息复用、识别推荐可修改、缺失才补问，不逐车削工步询问。第三步阈值与第五步实际值分开。此前待确认的问答方式已收敛；A/B范围下实际参数共用或分侧仍未定稿，整项暂保留needs-info，Execution: deferred，详见[PM-059](issues/59-operation-feature-direction-pairing.md)顶部最新决定。下方旧方案状态为讨论历史，不覆盖本次确认。
PM-059操作量补充：用户担心车削工步多是否需要逐一询问。助手建议系统后台分析工步、按工序汇总可修正，优先确认后续规则实际引用的对象，仅对缺失／冲突信息定向补问；具体交互尚未确认，不展开逐工步问答。沿用原工单，needs-info、Execution: deferred。
PM-059本次补充：用户确认主工序缺少加工对象／方位信息的问题，询问解决方式。助手提出逐工序补录与从完整路线整理可追溯对象候选后统一引用两种方式，推荐后者；具体方案待选择。主工序固定出现、对象描述与精加工触发分别保存为建议，不将未选方位当作所有方位，母路线候选不代表新零件全部具备。沿用[PM-059](issues/59-operation-feature-direction-pairing.md)，needs-info、Execution: deferred，仅讨论记录。
PM-062新增：用户要求移除第五步路线验证结果“工序工步树”右上角“复制 JSON”和“导出 JSON”按钮。范围已定位，ready-for-agent、Execution: deferred，仅记录；详见[PM-062](issues/62-remove-route-output-json-actions.md)。
PM-061最新确认：用户已认可头部/列表边缘压缩，并确认工序卡片采用摘要与工步入口同行、工步按需展开、内边距5～6px和卡片间距2px；普通收起卡片目标32～36px，实际空间收益实施后验证。更新为ready-for-agent，Execution仍为deferred，详见工单。
最新讨论：[PM-062](issues/62-remove-route-output-json-actions.md)新增路线验证结果头部两个JSON按钮移除需求；[PM-061](issues/61-compact-route-merge-panels.md)头部压缩及卡片紧凑方案均已确认。两项均ready-for-agent、Execution: deferred，仅记录，待统一实施。此前[PM-060](issues/60-configurable-template-mapping-visibility.md)已确认通过部署级配置开关控制第六步分组模板映射可见性：默认可见，不可见时隐藏入口/导航并保留映射数据，重新启用后继续使用，内部保留第六步编号。配置文件具体路径、是否复用现有包元数据字段及实施批次待设计，Status: ready-for-agent、Execution: deferred。关联PM-007及PM-020～PM-023。[PM-059](issues/59-operation-feature-direction-pairing.md)已确认保留方位单选、“所有方位”覆盖A/B且任一侧满足完整条件即可。用户进一步澄清：车A/B为主工序、磨端面仅选精度而未选方位时，系统如何生成因素表；重点是加工对象和方位来源。已核对当前只从有效规则引用字段生成输入，“轴端面”取配置映射，并无从前序主工序自动绑定A/B表面机制；未选择方位不能当成已选择所有方位。此前两侧精度差异／分侧输入只是助手建议，未获确认。needs-info、Execution: deferred，仅讨论，不改产品或数据。
本轮交付：[PM-058](issues/58-full-validation-package-20261108.md)已完成当前工作区的全量复核并生成新的`full`完整包；后端2039通过/110跳过、前端1281通过、构建和Python3.8检查通过，隔离包烟测81项通过，真实浏览器首页及底栏检查通过。ZIP为`dist-win7/processmind-win7-full-template-20261108.zip`，SHA-256为`cd6c87a9b931f7688c1da5fcb330442b7d53b4429e2dbd213779cef1179a7b17`。正式项目数据、模型配置和服务保留；Win7实机及接收方模型网络仍待验证。
PM-038最新结论（2026-11-08）：用户在打包版测试中确认 VPN 是模型服务 HTTPS 握手失败的原因；此前具体责任端未定的诊断为历史状态。PM-038 仍等待用户验证第三步完整生成，本次未改代码、包、网络配置或项目数据。
本次讨论：[PM-012](issues/12-route-validation-factor-display.md)用户询问规则审核后的路线因素展示，并明确只讨论。已核对第五步读取当前已保存规则、左侧材料／加工因素／人工安排与右侧路线的现状；本次未新增或确认改动，工单保持done，不启动产品修改，正式数据和服务保留。
专项复审完成：[PM-055](issues/55-finalize-reset-duplicate-recognition.md)重复解析、[PM-056](issues/56-reset-candidate-loses-confirmed-answer-mode.md)类型丢失、[PM-057](issues/57-preprocess-reset-reuses-stale-job.md)旧任务复用及状态注册间隙均已修复，回归先失败后通过。最终后端2039 passed/110 skipped、前端1281 passed，构建/Python3.8检查通过；独立审查无剩余重要缺陷，Tabbit全量重答、重识别、往返、重载和人工Bool保留通过。见[专项验收](evidence/pm-053-reset-audit-20261108.md)。
专项交接完成：[PM-053](issues/53-finalize-refresh-rebuilds-route-cache.md)正式数据库及20份PDF备份于`.runtime/db-backups/before-reset-audit-clear-20261108-164143/`，现有删除API已清空项目7及业务数据和上传文件，保留模型配置/提示词/预置/ID高水位。正式8000/5173运行，Tabbit打开正式上传空首页、底栏可见；清理57项旧项目浏览器缓存。交接后用户新建数据继续保留，不再次清空。历史项目7旧回答无法恢复，测试副本未回灌。
已完成：[PM-054](issues/54-simplify-analysis-refresh-actions.md)第三步保留“重新回答全部”，删除“刷新路线”；第四步删除顶部“刷新结果”。Tabbit 往返验证后40条规则卡片仍在，异常重试继续位于底栏。
当前执行：[PM-047](issues/47-full-functional-audit.md)全项目功能审查与缺陷修复，用户直接授权。按[审查计划](../../docs/superpowers/plans/2026-11-06-full-functional-audit.md)覆盖现有功能、跨步状态和异常边界；先隔离验证再最小修复，保留正式数据/设置/服务与既有工作区，不自动清空或重新打包。
本轮发现：[PM-048](issues/48-zero-factor-value-presence.md)因素数值0被当作空值，已两条RED复现，纳入PM-047直接授权修复；不改变硬度或Ra合法域。
本轮新增并已修复：[PM-049](issues/49-stale-route-merge-after-reextract.md)重新提取期间旧归并结果可能写回、[PM-050](issues/50-upload-merge-lock-order.md)上传与归并锁顺序反转；均已加入并发回归，最终全量复测进行中。
本轮新增并已完成：[PM-051](issues/51-slash-preparation-question-classification.md)第三步将组合准备工序误判为加工工序，已修复；补齐“下料准备/开料/切料”的前后端分类边界后，再连续完成五轮不同范围审查。最新后端 `2027 passed/110 skipped`、前端 `1267 passed`，生产构建和 Python 3.8 静态检查通过；当前 8000 API 尚未重载本次源码，手工复测待安全重载。
本轮新增并已完成：[PM-052](issues/52-project-delete-executable-revisions.md)项目删除漏清理可执行规则版本，导致标准化路线删除时触发外键失败；已补充分段删除和回归测试，后端全量通过，重启服务后真实项目清空验证通过。
本轮审查完成：[PM-047](issues/47-full-functional-audit.md)五轮功能审查已完成。最终后端 2017 passed/110 skipped，前端 89 个测试文件/1255 项通过，生产构建、Python 3.8 源码兼容检查及现有 full Win7 包校验通过；项目 6 已按授权清空，模型设置、提示词和用户 Tabbit 新首页保留。真实外部模型网络、Win7 Pro 实机和 CAD 接收端仍未验证。
当前跟进完成：[PM-044](issues/44-align-rule-card-actions.md)23:39截图的右侧重复确认标签已移除，done；关联/Bool/条件确认状态仅在摘要显示，待确认按钮、编辑取消及主工序展开正常。相关172项测试与vue-tsc/Chrome109构建通过，Tabbit实际组件及375px视口检查通过，见[跟进验收](evidence/pm-043-045/card-status-acceptance.md)。保留用户数据、原页签和服务，无重新打包。
当前完成：rule-review-polish及实施中追加的[PM-046](issues/46-mapping-header-left-alignment.md)已完成，共PM-018/043/044/045/046五项done。最终前端89文件1253项通过、vue-tsc及Chrome109构建通过；独立审查发现的刷新期间旧列表批量操作和历史编辑双按钮挤列已补回归RED→GREEN并修复。详见[本批验收](evidence/pm-043-045/acceptance.md)。
当前最终决定：[PM-044](issues/44-align-rule-card-actions.md)详情箭头依用户明确选择置于主工序标签后，替代右侧操作组最前的中间方案；右侧选择/确认/修改三列贴右对齐。[PM-046](issues/46-mapping-header-left-alignment.md)共享标题信息区显式row，映射标题与信息区左起点一致。
本批交付：[PM-043](issues/43-template-mapping-return-to-validation.md)映射返回及未保存确认、[PM-018](issues/18-confirm-all-finalize-rules.md)批量操作融入顶部、[PM-044](issues/44-align-rule-card-actions.md)卡片对齐、[PM-045](issues/45-shared-rule-editor-redesign.md)第三/四步共用编辑器重设计均按[设计](../../docs/superpowers/specs/2026-11-06-rule-review-polish-design.md)与[计划](../../docs/superpowers/plans/2026-11-06-rule-review-polish.md)完成。Tabbit实际第四步编辑、映射返回/继续保留/确认丢弃及桌面窄屏通过。第三步当前锁定，未为重跑流程修改用户状态；共用组件回归及绑定检查通过。Figma被Starter配额拦截，未生成新稿；Win7未实测。用户数据、原页签、服务和原ZIP保留，本批无清空/提交/推送/重新打包/发布。
授权历史：PM-018同质化讨论曾deferred，后用户明确将选择与确认已选融合上方并启动本批，已由上述实施结果替代，不再作为待确认项。
当前交付完成：[PM-042](issues/42-full-validation-package.md)复查并生成full完整验证包，done、authorized-directly。纯准备合并名／次数边界补齐；Python3.8后端2013通过／110跳过、前端1244通过、构建及暂存／解压件各81项烟测通过，ZIP完整性和逐文件哈希通过。`dist-win7/processmind-win7-full-template-20261106.zip`约44.1MiB；不带本机项目数据或密钥，完整模板功能开启；Win7实机及接收方模型网络待对方验证。详见[PM-042验收](evidence/pm-042/acceptance.md)。本机8000／5173服务、用户数据及页签保留。
当前完成：[PM-041](issues/41-export-structured-process-phase.md)路线验证导出误报“下料缺少加工精度”，done、authorized-directly。下料／备料按辅助工序处理，真正加工精度从冻结结构化阶段及确认映射读取。前端1230项、后端2003项通过／110跳过，构建及浏览器原48工序故障包三表ZIP验证通过；本地后端已生效，重载前后业务数据／规则版本／模型设置保留。详见[PM-041验收](evidence/pm-041/acceptance.md)，用户新版流程及Win7实机仍待复测。

当前补充：[PM-039](issues/39-reset-dialog-visual-consistency.md)重置弹窗主题统一及[PM-040](issues/40-compact-rule-review-cards.md)规则审核区域紧凑样式均已完成，done、authorized-directly。审核按钮28px、正文12px、工序名13px；同一窗口典型卡片约201px降至141px，完整可见由2张增至3张。Tabbit交互／响应式检查、最新1213项前端回归及TypeScript／Chrome109完整构建通过。仅修改三处组件scoped CSS，模板／脚本与原快照一致；项目数据、用户页签、服务及模型设置保留。Win7实机未测。

当前阶段：2026-11-06下午，[PM-036](issues/36-step3-remove-search-move-status-to-top-navigation.md)和[PM-037](issues/37-workflow-header-height-match-template-mapping.md)已按“先改第一个和第二个”授权完成，Status: done。第三步搜索／独立横栏已移除、状态移入顶部，六页标题栏已统一并经Tabbit验证，主体增加88px。详见[标题栏验收](../../docs/superpowers/reviews/2026-11-06-compact-workflow-headers-acceptance.md)，其中保留共享工作区PM-038新增测试实施中造成的全量复测限制。[PM-038](issues/38-model-connection-failure-blocks-step3.md)由独立模型设置专项处理，本批不修改其代码或设置，不据此宣称模型连接恢复。正式项目数据、用户原页签和服务均保留。

本轮实施授权更新：用户明确“那先改第一个和第二个”，仅启动PM-036／037，Execution为authorized-in-batch: compact-workflow-headers。先前仅分析／deferred记录由本次授权替代。按[标题栏设计](../../docs/superpowers/specs/2026-11-06-compact-workflow-headers-design.md)及[实施计划](../../docs/superpowers/plans/2026-11-06-compact-workflow-headers.md)修改；PM-038保留诊断，当前项目数据及服务继续保留。

PM-038实施结果：用户在专项分析后明确“你直接修正这个”，已按[设计](../../docs/superpowers/specs/2026-11-06-pm038-model-settings-design.md)和[计划](../../docs/superpowers/plans/2026-11-06-pm038-model-settings.md)完成配置一致性、非阻塞列表、测试有效性、整组保存和连接／第三步反馈修正。后端1999通过／110跳过、前端1213通过、构建及独立审查通过，详见[专项验收](../../docs/superpowers/reviews/2026-11-06-pm038-model-settings-acceptance.md)。诊断时保留服务，实施生效时确认无运行任务后仅重载8000本地后端一次；设置文件及25张业务表行数前后一致，5173服务和项目6保留。验收时TLS失败场景约5秒反馈；随后用户已于2026-11-06实测模型连接成功，最新连接状态通过。第三步完整生成与耗时尚未反馈，PM-038保持in-progress等待该项结果；此前握手故障责任端仍未确定。未更改网络、模型配置或清空数据。

前次PM-038专项分析：已完成[专项分析及隔离复现](evidence/pm-038/model-settings-analysis.md)，确认五项设置问题。15:08当前TLS仍约5秒中断，具体链路责任端未定；相关既有前端11项、后端29项通过。当时仅分析，后由上述直接修正授权替代。

前次分析进展：PM-038已最小复现HTTPS握手约5秒被断开，HTTPX默认／直连诊断及curl同样失败，用户Tabbit既有服务页也为ERR_CONNECTION_CLOSED；应用三次尝试加退避约21秒、第三步泛化错误掩盖连接原因。具体关闭连接的隧道／网关或服务端仍未确定，不能宣称模型已恢复。详见[脱敏诊断](evidence/pm-038/connectivity-analysis.md)。PM-036／037已定位到独立搜索状态栏与各页不同字号／留白覆盖，助手建议状态并入原标题栏、统一映射页紧凑尺寸，当时仍待本轮讨论收敛；该次未改产品或用户数据。

实施前确认（历史，已由下述round4-all实施结果替代）：[PM-035](issues/35-compact-rule-package-export.md)用户选择“按照样式包读取”，确定以提供样包的三个 JSON 数组及字段／类型／条件表达作为对外交付兼容目标，精简须在此协议范围内进行。关闭接收端格式选择；当前规则等价转换及字段裁剪留待设计核对，ready-for-agent、Execution: deferred。未修改产品导出或项目数据。
实施前演示（历史）：按用户要求为PM-035生成[当前项目复杂三表样例](evidence/pm-035/demo-2026-11-06/演示说明.md)，21工序／16因素／21规则，7组原生与本地读取引擎案例对照通过。当前48节点与最近invalid规则版本不一致，示例明确来源和演示设定，不作为正式全量导出；未修改产品或数据，Execution仍deferred。
实施前编号确认（历史）：PM-035用户已确认内部与对外编号分开、导出使用短编号、同步三表引用、内部保存长短对应关系，以及同对象重复导出／补充映射／排序后编号稳定。前缀、补零位数及具体分配存储策略由助手整理设计，无需重复询问既定业务；内存短编号替换的结构校验及7组演示路线对照已通过，持久化及接收端部署兼容仍待实现验证。Execution继续deferred。

前轮完成：round4-all已完成实施及验收：PM-024界面、PM-030～035及第三步后规则链路审查修复。正式业务已于2026-11-06 14:08一致性备份后清空，8000／5173重启、空上传首页打开，设置／提示词及ID高水位保留。用户已在Tabbit确认底栏恢复。详见[第四轮验收单](../../docs/superpowers/reviews/2026-11-06-system-improvements-round4-acceptance.md)；备份`.runtime/db-backups/before-round4-manual-review-20261106-140806/`。交接后用户新增数据继续保留，不再次清空。保留脏工作区，没有提交、推送、打包、发布。

前轮证据：后端1978通过／110跳过，前端1167通过，Chrome109构建与147个app文件Python3.8静态语法通过；实际隔离第三步48/48采纳、第四步40/40确认、第五步生成、第六步映射保存／三表下载及稳定编号均验证。原车削A侧偶现完整名称未重现，已确认跨推理批次混用竞态并修复；Tabbit曾不见底栏后恢复的确切根因未证实，Chrome模拟视口遗留已单独清理，不能混为同一根因。Win7及外部CAD部署仍未测。

授权历史：本轮先获PM-024界面及PM-030～034实施授权，后追加PM-035；按[第四轮设计](../../docs/superpowers/specs/2026-11-06-system-improvements-round4-design.md)和[第四轮计划](../../docs/superpowers/plans/2026-11-06-system-improvements-round4.md)完成。下方deferred及未实施段落按各自时间保留，不覆盖本节当前结果。

前次阶段：2026-11-06用户已提供本轮全部6项反馈：PM-031、重新打开的PM-024、PM-032、PM-033、PM-034、重新打开的PM-030；已完成记录，进入集中讨论，执行均保持deferred。讨论范围与助手待确认建议见[本轮讨论提纲](round4-discussion-outline.md)。上一轮round3-all（PM-024～PM-030）已完成当轮修复和四遍排查，不能视为本轮新增反馈已解决；验收步骤、实际验证与Figma/Win7限制见[第三轮验收单](../../docs/superpowers/reviews/2026-11-06-system-improvements-round3-acceptance.md)。保留正式项目5与20份PDF，没有再次清空；未提交、推送、打包或发布。

前轮完成记录：第二轮PM-014～PM-023全部10项已完成实施、完整回归及独立审查，状态done；最终2条Important已集中修复并窄复核通过。已按用户要求备份清空旧业务数据、重启并打开浏览器，供用户自行走流程。未提交、推送、打包或发布；Win7实机/CAD联调仍未测。此为既有验证记录，不代表用户新反馈均已覆盖或修复。

上一轮完成记录：原五批十二项已确认需求全部完成并关闭；新增PM-013已按直接授权修复并关闭，累计13项。原独立审查与跟进发现的五项重要缺陷已修复复核；上一轮最终后端1764通过/110跳过、前端888通过，构建及变更后端Python3.8语法检查通过。此为既有验证记录，不代表本轮走查问题已得到验证或修复。保留原工作区修改，未提交、推送、打包或发布；Win7实机验证仍未执行。

前次只读分析记录（已由本次实施替代）：[PM-024](issues/24-step3-generation-latency-and-progress.md)按用户要求完成[只读耗时分析](evidence/pm-024/2026-11-06-latency-analysis.md)：真实日志35～135秒后422及约190秒超时，当前48节点与旧41节点指导缓存不符，一次用户消息约5.7万字符；本地复现下料缺少特征候选导致整包校验失败。助手建议先解决题目/候选/校验不一致，再缩减模型重复输出、按节点复用及小批处理；没有重放模型或修改产品/用户数据，Execution继续deferred。

本次补充：[PM-024](issues/24-step3-generation-latency-and-progress.md)用户要求生成提示越简洁越好，后续沿底栏简短状态及按需详情方向统一精简，性能完成不等于界面已完成；[PM-030](issues/30-compact-template-mapping-toolbars.md)补充中间布局字体整体适当缩小以增加可见内容，具体字号未定，行高／间距／内边距配合调整为助手设计建议。仅更新记录，未修改产品样式。

前次澄清：[PM-031](issues/31-route-merge-name-after-rerun.md)用户明确仅排查“全部合并后车削A侧名称偶现变复杂”的原因。助手扩出的命名原则建议已撤回，仅保留历史，不新增命名规范；本项转ready-for-agent、Execution继续deferred。下一步集中整理实施依赖与验收顺序，见[讨论提纲](round4-discussion-outline.md)，不再逐项重复询问既定业务要求。

前次确认：[PM-033](issues/33-regeneration-and-adoption-state-conflict.md)用户回复“可以”，确认生成中／失败／已就绪／采纳成功四类状态区分、旧采纳提示撤下及真实采纳数，并确认上述提示统一在下方导航栏，详情沿用PM-032向上浮层。本项转ready-for-agent、Execution仍为deferred；PM-024顶部短状态建议由底部状态提示确认替代，可选进度条仍以实际性能和既定顶部方向设计。未启动产品修改。

前次确认：[PM-034](issues/34-duplicate-route-validation-navigation.md)已确认保留右下角“进入路线验证”、移除右上角重复按钮，ready-for-agent、Execution仍为deferred。[PM-030](issues/30-compact-template-mapping-toolbars.md)沿用第二步布局参照，具体尺寸留待设计。

前次确认：[PM-032](issues/32-page-notifications-in-bottom-navigation.md)已确认底部简短摘要＋查看详情入口，点击后向上弹出详情浮层，底栏高度不变、中间主体不被挤压；ready-for-agent、Execution仍为deferred。

前次讨论记录：[PM-024](issues/24-step3-generation-latency-and-progress.md)确认优先优化生成耗时，足够快时允许去掉进度条；[PM-032](issues/32-page-notifications-in-bottom-navigation.md)当时先确认底部简短摘要＋查看详情，向上浮层方式当时为待确认建议，本次已确认。各项均继续deferred。

本轮收集记录：本轮第1项[PM-031](issues/31-route-merge-name-after-rerun.md)记录重新推理与全部合并后的名称变化；第2项补充并重新打开[PM-024](issues/24-step3-generation-latency-and-progress.md)，记录规则分析等待仍久及生成进度融入顶部导航（进度条是否保留以最新讨论为准）；第3项新增[PM-032](issues/32-page-notifications-in-bottom-navigation.md)，记录全系统类似页面提示统一融入底部导航；第4项新增[PM-033](issues/33-regeneration-and-adoption-state-conflict.md)，记录重新回答失败／生成中却仍提示已采纳41道、当前统计48道的状态及计数问题；第5项新增[PM-034](issues/34-duplicate-route-validation-navigation.md)，记录规则定稿页右上角与右下角“进入路线验证”入口重复；第6项补充并重新打开[PM-030](issues/30-compact-template-mapping-toolbars.md)，记录映射页参照第二步、压缩上下导航并扩大中间两栏。已提供的截图均已归档，进入集中讨论；助手建议与用户方向分别记录，未独立复现、修改产品代码或项目数据。

上一轮处置：PM-024～PM-030均已按自主实施授权完成，包含生成进度/重试、固定首问、有效推荐、Bool审核衔接、全条件中性标签及紧凑映射。后续四遍检查发现的相关缺陷已修复并留回归。Figma账户配额耗尽，未写新画板；代码布局已实测。上一轮旧“只记录/待讨论”段落作为历史保留；本轮记录约束以2026-11-06最新要求为准。

前次实施授权：用户明确“没有的话你就可以开始实施修改了”，已建立[正式实施计划](../../docs/superpowers/plans/2026-11-05-system-improvements-round2.md)，启动round2-all；保留现有工作区基线，按任务独立实现与联合验收。该轮已完成，不作为本轮PM-024以后新项的实施授权。

前次确认：用户批注“可以按照这样来做”，确认提示词修改用于后续新生成、保留已有回答和审核规则；确认删除后排序再恢复保留其它工步已调整的顺序、恢复项统一未映射。已回写[PM-014](issues/14-step3-prompt-based-question-guidance.md)、[PM-021](issues/21-delete-mapped-and-unmapped-steps.md)、[PM-023](issues/23-reorder-steps-within-operation.md)及[统一设计](../../docs/superpowers/specs/2026-11-05-system-improvements-round2-design.md)。PM-014转ready-for-agent，现9项ready、PM-016一项needs-info，Execution全部deferred；不扩大为内部技术策略全量批准或产品启动授权。

前次确认：用户在钻孔例说明后回复“那可以按照你这样来做”，确认[PM-014](issues/14-step3-prompt-based-question-guidance.md)中手动回答与一键采用推荐共用同一套问题、候选和规则转换，相同选值生成相同规则，手动改选使用实际答案。已同步[统一设计草案](../../docs/superpowers/specs/2026-11-05-system-improvements-round2-design.md)，不扩大为整体方案或实施授权；当时8项ready-for-agent、PM-014/016两项needs-info、10项deferred。

前次方案整理：用户要求“继续”，完成[第二轮统一设计草案](../../docs/superpowers/specs/2026-11-05-system-improvements-round2-design.md)的整理与独立审阅，供集中审核。草案汇总问答生成与更新、共用条件、批量确认、IT输入和映射删除/排序/豁免的保存导出，以及全系统Figma覆盖安排；生效和恢复位置等技术策略仍为助手建议。8项ready-for-agent、PM-014/016两项needs-info及10项deferred均保持，不启动产品修改或Figma。

前次处置：用户回复“可以”，确认[PM-022](issues/22-inline-leaf-group-waiver.md)待映射可豁免、已豁免可取消、已映射禁用豁免的行内状态，本项转ready-for-agent。PM-015、017～023共8项具备实施条件但继续等待统一实施；[PM-014](issues/14-step3-prompt-based-question-guidance.md)文件维护方向及[PM-016](issues/16-system-interface-visual-consistency.md)视觉方向已明确，提示词更新生效/异常处理、具体设计稿与验收等仍需在统一方案中整理，不把它们写成已全部获批。下一阶段建议汇总设计与排期，既有业务决定不重问。本轮仍共10项，Execution全部保持deferred。

前次处置：2026-11-05用户要求当前系统移除试用功能，新增[PM-013](issues/13-disable-trial-checks-in-full-edition.md)已直接授权修复。完整版不再启动或定时执行试用检查；实际网站已更新并经浏览器阻断状态请求验证正常，19份上传文件及模型设置保留，现有服务和分析任务未重启。

前次布局处置：2026-11-05用户指出上传主输入区域双栏留白，归入PM-005布局收尾，改为整行单栏并进行浏览器复核。

前次处置：用户确认PM-012左右双栏与左侧三块布局；确认R03/B02各工序只检查自身明确要求；取消保护要求自动触发镀铜的B03分支。用户授权助手选Ra阈值，现选Ra≤0.8 μm作为可改起始配置，以磨削粗糙度备用分支为起点，不替代IT7/暂定IT6推荐或代填第五步实际值。用户随后明确授权按五批实施全部已确认需求；第一批PM-005/PM-006已完成验证，当前进入PM-004性能复核。

排期范围更新：当前需求共12项。用户已授权按五批实施：第一批PM-005/006，第二批PM-004，第三批PM-001/002/003/010/011，第四批PM-007/012，第五批PM-008/009。PM-011仅按当前恢复范围实施，不恢复全部旧方案。

**第三步问题树当前整理入口**：[v2.9集中稿](operation-question-trees-review-v2.md)，七类共21例，要求判断及Ra授权选值已收敛；对应[三元组稿v3.7](operation-condition-triples-review.md)，撤除B03后有效条件项12条。其余问句由助手按既定业务统一措辞，不代表所有历史草案逐句获批。旧稿v1.18仅保留讨论历史；最新推荐详表见[推荐清单](step3-recommendation-gaps-review.md)，第三批实施按计划进行。

## 使用约定

这是本轮系统改进的统一入口。继续讨论时读取本文件及相关工单，无须依赖上一段聊天的完整上下文。

1. 新问题先分配编号 PM-001、PM-002……并建立独立工单；同一问题继续更新原工单。
2. 用户明确同意的内容记为“已确认”；只认可方向的内容记为“方向已确认，细节待讨论”；助手建议单独标注。
3. 用户说“合理”“按这个来”用于确认对应讨论结论；当前统一实施约定下，不据此自动开始改产品代码。
4. 每次实质性讨论结束，更新工单的结论、开放问题和讨论记录；回复中简要报告本次记入的编号。
5. 用户明确要求实施时，按其指定范围组批；“统一实施”未指定具体范围时默认只纳入当时已确认且具备实施条件的项。遇到尚未解决且影响结果的决定，只暂停依赖该决定的工单。
6. 实施前冻结该批次的范围、设计和验收要求，再按 Superpowers 流程拆解技术计划。详细计划放在 `docs/superpowers/plans/`，并从对应工单链接过去。
7. 完成以实际验证为依据；部分完成、未验证和待定项分别记录。

使用仓库已有的本地 Markdown 工单约定，见 [工单规则](../../docs/agents/issue-tracker.md) 与 [ADR-0001](../../docs/adr/0001-local-markdown-issue-tracker.md)。

## 状态与执行授权

业务决定与执行状态分别记录：

- **决定状态**：已确认 / 方向已确认、细节待讨论 / 待讨论 / 已被替代。
- **工单状态**：沿用 `needs-info`、`ready-for-agent`、`in-progress`、`blocked`、`done`。
- **执行授权**：`Execution: deferred` 表示等待统一实施；用户明确启动某批次后才改为 `authorized-in-batch: <批次编号>`。

`ready-for-agent` 不代表已获得本轮实施授权。维护讨论文档本身属于当前已授权范围。

## 改动清单

| 编号 | 改动 | 决定状态 | 工单状态 | 执行授权 | 依赖 |
| --- | --- | --- | --- | --- | --- |
| [PM-001](issues/01-analysis-readonly-after-finalize.md) | 进入规则定稿后，第三步只读；保留全量重答入口 | 已确认 | done | authorized-in-batch: all-five-batches | 无；无历史锁定记录的项目按未锁定初始化 |
| [PM-002](issues/02-question-rule-alignment.md) | 第三步问答与规则修改四种出现方式对齐 | 已确认；各工序查自身要求，撤除自动镀铜，Ra起始值按授权选定 | done | authorized-in-batch: all-five-batches | 与 PM-001 一致；与 PM-003 联合设计 |
| [PM-003](issues/03-question-framework-and-wording.md) | 精简问答，采用工艺师口吻，支持通用分析框架 | 业务框架已确认；七类21例按既定含义统一措辞，非历史草案逐句获批 | done | authorized-in-batch: all-five-batches | PM-002 的规则输出边界 |
| [PM-004](issues/04-step2-parse-performance.md) | 第二步解析并发、缓存复用与重复解析优化 | 方向及单列第二批已确认 | done | authorized-in-batch: all-five-batches | 已完成并发、缓存和失效回归；当前 20 PDF 本地基准下降 69.1%，真实模型/Win7待测 |
| [PM-005](issues/05-remove-project-references.md) | 完整移除项目辅助参考资料功能 | 功能及历史资料直接清除已确认，不归档 | done | authorized-in-batch: all-five-batches | 已完成前后端及下游清理；已验证旧参考数据清理与主文档/知识证据保留 |
| [PM-006](issues/06-pdf-only-process-document-upload.md) | 工艺规程上传仅允许 PDF | 上传范围与首期文字/表格 PDF 边界已确认；客户无旧版本，排除历史非 PDF 兼容迁移 | done | authorized-in-batch: all-five-batches | 已完成前后端 PDF 限制与内容校验；规则包 JSON、模板 XML 等入口保留 |
| [PM-007](issues/07-template-mapping-after-route-validation.md) | 模板分组映射移至工艺路线验证之后 | 主流程、最后一步导入模板及规则修改后删除旧验证结果均已确认 | done | authorized-in-batch: all-five-batches | PM-001～PM-003及PM-010；可验证规则版本、候选与保存接口由实施设计衔接 |
| [PM-008](issues/08-exclude-process-steps-from-template-mapping.md) | 模板映射中允许人工忽略未映射工步 | 忽略/恢复行为及工具栏布局已确认 | done | authorized-in-batch: all-five-batches | PM-007 完整母路线与规则包边界 |
| [PM-009](issues/09-waive-template-group-feature-mapping.md) | 允许模板分组声明无需特征映射 | 逐叶子按钮、自主豁免、状态区分及更换模板后清除旧豁免均已确认 | done | authorized-in-batch: all-five-batches | PM-007 可选映射和规则包边界；原因记录及保存清理由实施设计处理 |
| [PM-010](issues/10-configurable-step3-question-guidance.md) | 第三步可配置提示词、特征映射与方位候选 | 通用框架＋项目配置及提示词/候选/规则共用已确认 | done | authorized-in-batch: all-five-batches | PM-002/PM-003 的既定问题树与规则输出；不依赖 PM-011 产品实施 |
| [PM-011](issues/11-step3-recommended-answer-adoption.md) | 一键采用推荐回答适配新问题树及规则输出 | 当前项目9项推荐内容已补齐；两处辅助节点均主工序，研顶尖孔Bool为倾向、IT6暂定 | done | authorized-in-batch: all-five-batches | PM-010配置；当前41节点推荐表；就恢复范围准备设计，不自动恢复全部旧方案 |
| [PM-012](issues/12-route-validation-factor-display.md) | 路线验证因素栏与工序规则对齐 | 材料选择、精加工对象展示、左右双栏与左侧三块组织均已确认 | done | authorized-in-batch: all-five-batches | PM-002/PM-010/PM-011；第四步当前规则及PM-007验证结果失效处理 |
| [PM-013](issues/13-disable-trial-checks-in-full-edition.md) | 当前完整版移除试用检查及整页拦截 | 用户直接要求立即移除 | done | authorized-directly: 2026-11-05 | 显式basic-trial打包约定；现有业务数据保留，浏览器验证完成 |
| [PM-014](issues/14-step3-prompt-based-question-guidance.md) | 第三步取消配置按钮，改由项目提示词文件指导问答与推荐 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-010后续调整，关联PM-011及PM-002/003既定问答与规则语义 |
| [PM-015](issues/15-step3-opening-question-wording.md) | 第三步各问题树首问及选项采用自然的工艺师口吻 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-003后续反馈，关联PM-014提示词维护及PM-002规则语义 |
| [PM-016](issues/16-system-interface-visual-consistency.md) | 全系统界面视觉与组件风格统一优化，含顶部提示条等消息样式 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-014取消配置按钮与PM-015文案调整；后续确定完整页面及组件范围 |
| [PM-017](issues/17-condition-editor-align-confirmed-triples.md) | 条件编辑器字段、判断关系及候选值与已确认三元组对齐 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-002及三元组v3.7有效总表、特征映射；关联PM-010/012/014 |
| [PM-018](issues/18-confirm-all-finalize-rules.md) | 规则定稿增加一键确认全部规则 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-002规则审核；PM-016统一视觉 |
| [PM-019](issues/19-validation-parameter-range-and-presentation.md) | 路线验证参数样式与精度等级上下限约束优化 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-012及精度基线；PM-016统一视觉；PM-017条件内容 |
| [PM-020](issues/20-simplify-template-mapping-header.md) | 移除模板映射页“模板文件名→零件标识”信息 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-007映射页；PM-016统一视觉 |
| [PM-021](issues/21-delete-mapped-and-unmapped-steps.md) | 模板映射中每个工步均可删除，不限映射状态 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-008后续范围变更；PM-007/016/022/023 |
| [PM-022](issues/22-inline-leaf-group-waiver.md) | 豁免按钮置于叶子节点行内，置灰并可取消恢复 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-009后续界面调整；PM-016统一视觉；PM-021/023工步操作 |
| [PM-023](issues/23-reorder-steps-within-operation.md) | 同一工序内部每个工步可上移或下移 | 已实施并验收；结果及边界见独立工单Answer | done | authorized-in-batch: round2-all | PM-007映射及导出；PM-016统一视觉；PM-021删除恢复/PM-022行内操作 |
| [PM-024](issues/24-step3-generation-latency-and-progress.md) | 优化第三步生成耗时，足够快可去掉进度条，仍需展示时精简到顶部 | 底栏精简状态及详情已实施，保留快速生成成果 | done | authorized-in-batch: round4-all | PM-014生成及PM-016反馈样式；关联PM-028/032/033 |
| [PM-025](issues/25-related-operation-name-only.md) | 关联工序选项只显示名称，去掉工序序号 | 已确认 | done | authorized-in-batch: round3-all | PM-002/015既有关联节点身份 |
| [PM-026](issues/26-neutral-condition-labels-and-full-list.md) | 三元组字段名去工序前缀，默认显示全部项目条件 | 已确认 | done | authorized-in-batch: round3-all | PM-017候选清单；PM-012因素作用域 |
| [PM-027](issues/27-fixed-opening-question-options.md) | 各工序首问固定主工序/用户决定/条件/关联/其他五项 | 已确认，替代PM-015首问选项随工序变化的对应部分 | done | authorized-in-batch: round3-all | PM-014稳定选值及PM-002规则输出 |
| [PM-028](issues/28-missing-recommendations-after-batch-adoption.md) | 一键采用后11处工序仍缺有效推荐 | 已实施；有效参考、身份及连续重试保护已验证 | done | authorized-in-batch: round3-all | PM-011/014推荐；关联PM-024 |
| [PM-029](issues/29-bool-rules-incomplete-in-finalization.md) | 第三步已选Bool，第四步却显示条件待补充 | 已实施；Bool解析及结构化交接已验证 | done | authorized-in-batch: round3-all | PM-002问答规则衔接及PM-018确认校验 |
| [PM-030](issues/30-compact-template-mapping-toolbars.md) | 映射页参照第二步，压缩上下导航并扩大中间两栏 | 主体密度、上下外间距及共用固定底栏已实测 | done | authorized-in-batch: round4-all | PM-016统一视觉及PM-020～023；PM-032/034共用导航布局 |
| [PM-031](issues/31-route-merge-name-after-rerun.md) | 排查全部合并后车削A侧名称偶现变复杂的原因 | 跨推理批次混用竞态已修复；原复杂名称完整偶现未重现 | done | authorized-in-batch: round4-all | 调查结果及限制见工单Answer；未新增命名政策 |
| [PM-032](issues/32-page-notifications-in-bottom-navigation.md) | 全系统类似提示在底部显示摘要＋查看详情，详情向上浮层展示 | 六页共用底栏及详情已实测；Tabbit已恢复、原现场根因未证实 | done | authorized-in-batch: round4-all | PM-016统一视觉；PM-024精简状态及PM-033状态区分 |
| [PM-033](issues/33-regeneration-and-adoption-state-conflict.md) | 生成与采纳状态分别在底栏显示，采纳数按本次实际保存成功数量 | 生命周期、当前上下文及真实保存计数已验证 | done | authorized-in-batch: round4-all | PM-024生成状态、PM-028推荐及PM-031路线变化；PM-032消息展示 |
| [PM-034](issues/34-duplicate-route-validation-navigation.md) | 规则定稿页仅保留右下角“进入路线验证”，移除右上重复入口 | 底部单一入口保留，确认门槛及进入验证已实测 | done | authorized-in-batch: round4-all | PM-007流程导航、PM-016统一视觉、PM-032底部导航布局 |
| [PM-035](issues/35-compact-rule-package-export.md) | 按用户样包协议导出精简三表及稳定短编号 | 三数组协议、SQLite稳定短编号及98组语义对照已验证 | done | authorized-in-batch: round4-all | PM-007导出；PM-002/012规则及因素语义；PM-021/023映射输出 |

| [PM-036](issues/36-step3-remove-search-move-status-to-top-navigation.md) | 第三步取消搜索及独立横栏，状态统计移到上方导航 | 筛选／空结果恢复通过，主体实增88px | done | authorized-in-batch: compact-workflow-headers | PM-016/032既有导航；PM-037统一高度 |
| [PM-037](issues/37-workflow-header-height-match-template-mapping.md) | 其它页面顶部标题工具栏高度以模板映射为基准 | 六页40px标题栏及底栏通过，窄屏长名重叠已修复 | done | authorized-in-batch: compact-workflow-headers | PM-016/030既有视觉；PM-036新增顶部状态 |
| [PM-038](issues/38-model-connection-failure-blocks-step3.md) | 修正模型设置缺陷及第三步连接失败反馈 | 设置修正及真实连接/第三步生成/第四五步联动已验收；外部偶发超时单列限制 | done | implemented-and-verified-20261120 | 当前设置／模型调用及PM-024/028/033生成链路 |
| [PM-039](issues/39-reset-dialog-visual-consistency.md) | 重新回答全部确认弹窗与系统主题一致 | 主题、桌面／窄屏／短视口、取消／关闭及键盘焦点已验证 | done | authorized-directly | PM-016统一视觉；共用第二／三／四步重置弹窗 |
| [PM-040](issues/40-compact-rule-review-cards.md) | 缩小规则审核区域按钮和字体，增加可见内容 | 典型卡片约30%压缩，同屏2张增至3张；交互／响应式及回归通过 | done | authorized-directly | PM-016/037既有视觉；仅卡片及列表工具条CSS |
| [PM-041](issues/41-export-structured-process-phase.md) | 区分准备与加工工序并修正导出精度来源 | 原48工序故障包三表ZIP、全量回归通过，本地生效 | done | authorized-directly | PM-035三表适配；冻结结构化母路线及映射精度 |
| [PM-042](issues/42-full-validation-package.md) | 复核并打full完整验证包 | Python3.8／前端全量、实际包烟测及ZIP哈希通过 | done | authorized-directly | PM-041、既有Win7运行时与full约定 |
| [PM-059](issues/59-operation-feature-direction-pairing.md) | 保留工序方位单选，明确精加工对象及实际参数作用范围 | 对象、A/B语义、单组实际参数及通用复用已实现，整链通过 | done | implemented / verified | PM-012、PM-002、PM-017、PM-019、PM-063 |
| [PM-060](issues/60-configurable-template-mapping-visibility.md) | 增加配置文件控制第六步分组模板映射可见/不可见 | product-features.json默认可见，隐藏/恢复保留映射数据 | done | implemented / verified | PM-007、PM-020～PM-023、PM-030、PM-058 |
| [PM-061](issues/61-compact-route-merge-panels.md) | 精简第二步路线归并双栏面板，扩大中间内容区域 | 双栏紧凑、工步邻名称、样本数54px右对齐，浏览器验证通过 | done | implemented / verified | PM-016、PM-030、PM-036、PM-037 |
| [PM-062](issues/62-remove-route-output-json-actions.md) | 移除路线验证结果头部的复制及导出 JSON 按钮 | 两处JSON按钮已移除，生成及规则包导出保留 | done | implemented / verified | PM-012、PM-035、PM-060 |
| [PM-063](issues/63-feature-based-route-validation-inputs.md) | 第五步按零件特征类别组织共享输入，减少跨工序重复填写 | 选中特征共享输入、原位展开及严格来源审计已实现，六类为实施组织选择 | done | implemented / verified | PM-012、PM-017、PM-019、PM-035、PM-059 |
| [PM-065](issues/65-eight-typical-route-benchmarks.md) | 分析客户八类典型工艺并核定路线生成基准 | 255条工序差异对照完成；扩充母路线、工步映射及实施方案待核定 | needs-info | deferred | PM-002、PM-003、PM-059、PM-063 |
| [PM-064](issues/64-compact-manual-process-checkboxes.md) | 第五步人工安排精简为复选框与名称并紧凑排列 | 复选框＋名称、自适应2/3/1列，默认false语义保持 | done | implemented / verified | PM-012、PM-016、PM-019、PM-048；与PM-063协调输入面板 |
| [PM-066](issues/66-align-analysis-finalize-operation-trees.md) | 第三、第四步左侧工序树及第五步右侧路线结果统一紧凑展示 | 三处树紧凑化，同容器完整行4→6，选择展开可用 | done | implemented / verified | PM-016、PM-036、PM-037、PM-061、PM-062 |
| [PM-067](issues/67-unify-numeric-threshold-controls.md) | 统一所有阈值控件的样式与大小 | 跟进28px问答/30px规则行，范围输入随面板换行，数值及键盘验证保持 | done | implemented / verified | PM-016、PM-019、PM-059、PM-066 |
| [PM-068](issues/68-finalize-unsaved-indicator-and-entry-flicker.md) | 调整第四步未保存提示并排查进入页面闪烁 | 初始/重复加载及刷新闪烁根因已修复，真实dirty保护保持 | done | implemented / verified | PM-016、PM-040、PM-045、PM-066 |
| [PM-069](issues/69-finishing-object-before-precision-basis.md) | 后续加工复用已确认特征/方位，只补缺项及本工序条件 | 通用复用已确认对象，只问缺项和独立精度，来源一致性及旧草稿已验证 | done | implemented / verified | PM-002、PM-003、PM-059、PM-067 |
| [PM-070](issues/70-complete-finishing-recommendation-chain.md) | 一键推荐复用已确认对象并贯通精加工条件 | 41采纳/32条件确认/冷5同版生成31步，真实HTTP验收通过 | done | implemented / verified | PM-011、PM-024、PM-059、PM-069 |
| [PM-071](issues/71-simplify-analysis-question-workspace.md) | 精简第三步规则问答统计、摘录与已保存结论展示 | 截图5块已移除，回答链/重答/完整链路通过 | done | implemented / verified | PM-066、PM-068～070 |
| [PM-072](issues/72-default-collapse-generated-process-steps.md) | 第五步生成路线工步默认收起，按需展开 | 已验证默认收起、单项展开与新结果重置 | done | implemented / verified | PM-062、PM-066 |
| [PM-073](issues/73-two-column-feature-inputs.md) | 第五步同类特征紧凑两列输入 | 桌面最多两列、窄面板单列，独立参数保持 | done | implemented / verified | PM-063、PM-064、PM-067 |
| [PM-074](issues/74-review-finalize-more-actions.md) | 精简第四步正常菜单原始描述与重新识别入口 | 常规入口移除，恢复默认及异常重试已验证 | done | implemented / verified | PM-053、PM-055、PM-068 |
| [PM-075](issues/75-remove-validation-precision-rule-hints.md) | 移除第五步精度输入下重复阈值说明 | 重复说明已移除，实际输入与规则保持 | done | implemented / verified | PM-063、PM-067、PM-073 |
| [PM-076](issues/76-review-finalize-evidence-display.md) | 移除第四步查看判定依据展示 | 展示整块移除，摘要与异常提示保持 | done | implemented / verified | PM-071、PM-074 |
| [PM-077](issues/77-align-validation-input-panel-style.md) | 统一第五步左侧输入区样式 | 左侧卡片/参数统一紧凑，右侧样式保持 | done | implemented / verified | PM-063、PM-067、PM-073 |
| [PM-078](issues/78-hide-mapping-reset-dialog-copy.md) | 隐藏映射时重新生成提示不提第六步 | 页面绑定及第二/三步取消弹窗已验证，文案使用可见性 | done | implemented / verified | PM-060 |
| [PM-079](issues/79-simplify-analysis-review-filters.md) | 第三步仅保留全部和待处理筛选 | 全部/待处理已合并，位置样式与第四步一致 | done | implemented / verified | PM-066、PM-071 |
| [PM-080](issues/80-compact-analysis-operation-header.md) | 精简第三步当前工序头部重复信息 | 重复头部精简，切换与导航已验证 | done | implemented / verified | PM-071、PM-079 |
| [PM-081](issues/81-compact-analysis-judgment-panel.md) | 第三步判定区域紧凑布局与蓝灰配色 | 判定区约缩短54%，配色/无效操作/窄屏已验证 | done | implemented / verified | PM-071、PM-079、PM-080 |
| [PM-082](issues/82-system-defect-audit-20261117.md) | 全系统现有缺陷审查、复现与修复 | 六项缺陷已修复，回归/浏览器/独立复核完成 | done | implemented / verified | 保留正式数据；PM-065仍deferred |
| [PM-083](issues/83-empty-route-workspace-success-state.md) | 第二步空路线误报成功 | 空业务结果进入恢复提示 | done | implemented / verified | PM-082 |
| [PM-084](issues/84-extract-retry-skips-workspace-reload.md) | 第二步失败后重试失效 | 强制刷新项目/路线并保留普通去重 | done | implemented / verified | PM-082 |
| [PM-085](issues/85-generation-input-change-invalidates-result.md) | 第五步输入变化仍误用旧结果 | 原始参数/响应/历史恢复一致性保护 | done | implemented / verified | PM-082 |
| [PM-086](issues/86-shared-ra-export-positive-domain.md) | 共享Ra导出漏正数下界 | 两种作用域边界一致 | done | implemented / verified | PM-082 |
| [PM-087](issues/87-failed-extraction-drains-parallel-tasks.md) | 提取失败后遗留任务回写状态 | 取消并等待同批任务收尾 | done | implemented / verified | PM-082 |
| [PM-088](issues/88-upload-cancellation-cleans-staged-files.md) | 上传取消遗留暂存文件 | 未提交清理/已提交保留 | done | implemented / verified | PM-082 |
| [PM-089](issues/89-release-review-full-package-git.md) | 发包前多轮复审、完整包与Git版本提交 | 20261117-r4完整包及本地提交d459731已核对，状态补记 | done | implemented / verified | PM-082～088；默认full |
| [PM-090](issues/90-delivery-guide-outdated-workflow.md) | 同步交付指南旧操作与旧导出协议 | 仅PDF/第五步导出/三数组与现有界面对齐 | done | implemented / verified | PM-089 |
| [PM-091](issues/91-conditional-required-export-compatibility.md) | 修正条件必填导出阻塞及误导性错误状态 | 三表与条件必填保留；读取器已更新；full修复包已交付 | done | implemented-and-verified-20261118 | PM-035、PM-063、PM-086 |
| [PM-092](issues/92-step3-invalid-model-response-diagnosis.md) | 第三步响应无正文与必答提示并现 | 分类/有限恢复及就绪保存保护已修正验收；历史原始响应原因未知 | done | implemented-and-verified-20261120 | PM-024、PM-038 |
| [PM-093](issues/93-full-release-git-20261120.md) | 提交推送当前修复版并交付full完整包 | 产品2044465已推送；full包、解压启动及摘要核对通过 | done | implemented-and-verified-20261120 | PM-038、PM-091、PM-092 |

## 已确认的跨项约束

- **当前新一轮范围（2026-11-06下午）**：PM-036／037按独立授权完成；PM-038由专项维护。第三步状态／数量迁到顶部不等于把生成错误、采纳反馈等所有消息改放顶部；PM-032底栏通知约定继续。页面标题栏以模板映射为基准，实际共同尺寸与响应式验收见本批记录。

- **当前执行口径（2026-11-06收尾）**：本轮已按最新授权完成。以下“未开始实施／仍deferred／只记录”按原讨论时间保留为历史，以顶部当前阶段、工单当前结果及第四轮验收为准。用户后续新反馈继续先记录，除非明确要求立即处理；不再次清空其新数据。

- **状态提示位置确认（2026-11-06，PM-033最新）**：生成中、失败、推荐已就绪及采纳成功四类状态提示均在下方导航栏显示，原因及重试详情沿PM-032向上浮层展示；不在中间或上下重复堆叠同一状态提示。PM-024仍优先优化实际耗时，是否需要可选顶部进度条按优化结果确定，未承诺具体耗时，未开始实施。

- **本轮提示最新确认（2026-11-06）**：PM-024优先优化实际生成耗时，足够快时允许去掉进度条，补充此前进度融入顶部的方向，进度条不作为必留元素；若仍需展示生成进度，沿用上方“规则分析”栏方向。PM-032已确认底部简短摘要＋查看详情，点击后向上弹出详情浮层，底栏高度不变、中间主体不被挤压；本项ready-for-agent但仍deferred。PM-033状态／计数一致性单独登记，不能以调整提示位置代替问题排查。没有产品实施。

- **新一轮先记录、再讨论（2026-11-06，最新要求）**：用户重新审核后将继续提供问题，明确要求先记录，然后一起讨论。新增问题建立独立工单，已有问题补充原工单，并区分实际现象、用户期望、待讨论项及助手建议；本轮执行保持`deferred`，上一轮自主修复授权不延伸到本轮反馈。当前只维护需求记录，保留现有代码、项目数据及运行状态。

- **最新round3-all授权（2026-11-05晚）**：用户要求助手自主完成PM-024～030及至少三轮排查修复，并交付明日验收文档。替代下方本轮只记录限制；七项均纳入本次范围。保留数据、未提交发布约束不变。设计：[第三轮设计](../../docs/superpowers/specs/2026-11-05-system-improvements-round3-design.md)；计划：[第三轮计划](../../docs/superpowers/plans/2026-11-05-system-improvements-round3.md)。

- **新一轮只记录（2026-11-05晚，PM-024起）**：用户明确后续问题先记录，后统一讨论。允许必要只读排查；旧round2-all授权不延伸到新反馈。保留用户当前项目和数据，不为排查刷新页面、重新生成、重启或再次清空。文档及截图归档属于已授权记录范围。
- **首问与显示最新调整（PM-025/026/027）**：关联候选去显示序号；条件字段去工序名前缀、默认展示全部项目条件；首问五项内容及顺序固定，条件因素在后续分支问。显示简化不改变内部节点身份、条件作用域或既定四类规则输出；保留旧工单决定及替代理由。

- **本次补充确认（2026-11-05，PM-014/021/023）**：提示词修改作用于后续新生成内容，已有回答和审核规则保留；工步删除后再排序，恢复时保留其它工步调整后的顺序，恢复项统一未映射。相关业务不再列为待用户确认。版本、缓存、完整顺序表等仍为实施设计，未获产品启动授权。

- **首问与选项口吻参考（2026-11-05，PM-015）**：用户认可钻孔“这类零件，钻孔这一步你一般怎么安排？”及其五选项的说法，可作为其他工序统一措辞的参考；结合各自既定因素调整，不机械套用孔/方位内容，不把尚未展示的新句子记作用户逐句确认。仅为口吻认可，既定主工序/Bool/条件/关联和其它出口语义保持，Execution仍为deferred。

- **本轮先记录、后集中讨论（2026-11-05，用户最新要求）**：当前PM-014～PM-023先讨论记录，再统一修复；新增排序需求纳入同一约定。界面优化后续借助Figma统一设计，当前不启动设计或产品实施。已确认的具体措辞与交互沿用，助手归纳和技术设计建议单独标注，不要求用户重复回答既定内容。

- **工步删除与恢复（2026-11-05，PM-021最新确认）**：每个工步均可删除，范围为本次映射清单与映射导出；已映射同步解除关联，保留恢复全部入口，恢复后统一未映射。替代PM-008此前仅未映射可隐藏的限制，旧决定及原因留工单历史；当前不实际删改。

- **新增工序内排序（2026-11-05，PM-023）**：用户要求同一道工序内每个工步可上移或下移。保存导出使用新顺序、映射身份随工步保留、与删除恢复的顺序衔接等由统一设计整理，详见独立工单；不混入工序本身重排或跨工序迁移，Execution为deferred。

- **叶子豁免界面及状态明确（2026-11-05，PM-022）**：取消树下方独立列表，叶子节点所在行提供豁免按钮；待映射可豁免，豁免后取消待映射字样、节点置灰，取消豁免仍可点击并恢复继续映射；已映射节点显示已映射，豁免按钮禁用。与PM-009原叶子级业务衔接，按PM-016统一用Figma整理界面；新调整仍deferred。

- **条件内容以已确认清单为准（2026-11-05，PM-017）**：用户要求条件编辑器使用此前确认的三元组内容，字段、判断关系及候选值共同对齐当前有效总表，不沿用已撤回的形位公差等历史方向。与PM-016视觉优化分开登记，现阶段保存截图并记录差异，后续统一核对修复，不要求重答已定业务。

- **界面优化范围（2026-11-05，PM-016）**：用户要求多处界面美观且风格一致，阈值输入、硬度输入、规则弹窗及后补的顶部黄色提示条截图只是示例，不能缩成只修截图所示位置或只修第三步。此类提示消息也纳入统一风格，不据此改变离开限制等业务逻辑。用户建议后续借助Figma，当前仅记录并保存截图证据，完整设计与实施范围待集中讨论。

- **新一轮提示词维护方向（2026-11-05，PM-014，最新决定）**：用户明确第三步不再提供“问题与推荐配置”按钮；最新调整为将相关指导维护在项目提示词文件中，不向终端用户暴露。此前已确认的系统设置提示词入口、模型配置/问答提示词双页签、大文本编辑及保存按钮，以及由此提出的设置入口改名均被替代，原因和旧决定保留在工单历史中。通用指导＋项目补充、特征/方位/推荐依据及模型实际参考的目标继续沿用，文件组织与更新触发待统一设计。现有实现主要由结构化配置及前端问题逻辑驱动，不能只改文件文字而不接入主问答和推荐链路。原一键推荐与第三步回答到第四步规则语义继续沿用，保留PM-010交付历史，新调整等待统一实施授权。

- **本轮四项批注确认（2026-11-04，替代下方早期待定状态）**：PM-012保留左侧因素/右侧路线，左侧分基本信息（材料）、加工因素（特征/方位/精度）、人工安排（Bool勾选）三块。R03/B02各工序只检查自身对应部位的明确要求，等于、是/否，不再讨论集合任一/全部。B03保护要求自动镀铜路径由用户明确撤除，镀铜Bool、除铜关联保持，不通过B02换名重引。用户授权助手选Ra阈值，现选Ra≤0.8 μm作为磨削粗糙度备用分支的可改起始配置，其他工序按自身要求配置；不称PDF事实或通用标准，不替代IT7/暂定IT6、不代填第五步实际值。有效因素13→12条，问题树v2.9、三元组v3.7；PM-002/PM-003/PM-012改为ready-for-agent，其余措辞由助手依既定业务整理。旧状态与替代原因保留，Execution全部deferred。

- **以下为先前讨论记录**：涉及本轮已关闭的阈值、要求集合、保护充分性和布局待审，以本节首条及当前工单为准；不因历史文字再次要求用户确认。

- **Ra比较及两句问法确认（2026-11-04，本轮批注）**：用户确认粗糙度按同一对象的实际Ra要求值≤设定阈值判断，不据此选择具体阈值或全部快捷候选；确认淬火“这道淬火，什么情况下要做？”及末段检验“这处末段检验，以后是否固定安排？”两句。处理要求集合命中尚在解释，保护要求备用条件仅针对镀铜保护，用户询问范围不等于确认自动镀铜；当前镀铜Bool、除铜关联保持。PM-012此轮仅解释布局待审范围，不视为布局确认。两审核稿升v2.8/v3.6，Execution仍deferred。

- **精加工特征与实际值展示已确认（2026-11-04，PM-012）**：用户以“可以，可以按照这样来”确认，因素组显示工序名称、已确定加工特征，再填写对应实际精度或粗糙度；具体字段读取第四步当前有效规则。确认示例为磨外圆/研外圆显示“加工特征：外圆柱面（已确定）”，沿用精加工特征默认存在。替代上一轮该展示细节待审核的状态，原提案及确认经过保留于工单。A侧/B侧车削仍为主工序，不新增外圆存在性条件；八道特征＋方位条件工序不是完整特征字典。整体布局尚未确认，Execution仍deferred。

- **第五步不新增材料（2026-11-04，用户纠正）**：材料“其他/手动补录”属于前面配置环节；路线验证只从已配置材料中单选，整件共用一次，替代PM-012首次助手建议中的第五步材料手填。此决定不扩展为禁止IT/Ra实际值输入。首次钻孔、铣槽仅是举例，PM-012已补列当前八道特征＋方位工序，以及精加工、材料判断和Bool的范围；主工序、关联工序不重复输入，最终显示读取第四步当前规则。整体布局仍待审核，Execution仍deferred。

- **路线验证因素栏讨论（2026-11-04，建议未确认）**：用户询问新因素栏的显示和改动大小。现有页面双栏、输入字段平铺；当前项目已存规则包6项输入，尚无新方位组。新增PM-012记录现状及建议：沿用双栏，按零件基本信息、加工因素、人工工序组织；特征与单方位同组，材料共享、不同对象精度不混用，主工序和关联工序不重复输入。第五步填写实际零件值，字段依赖第四步当前规则，不能把第三步推荐阈值当输入事实。新布局及分组是助手建议，未由用户确认，不改变既定执行范围，Execution仍deferred。

- **PM-007/PM-009本轮收尾（2026-11-04，用户批注确认）**：分组模板在最后的可选映射步骤导入；第4步规则修改后删除旧验证生成结果，第5步使用修改后的规则重新生成，重新生成前不能依据旧结果导出。更换新模板时清除原模板全部叶子豁免记录，不保留或继承；新模板需要豁免时由用户重新逐叶子操作。上述业务项从待讨论移为已确认，两工单改为ready-for-agent，Execution仍deferred，具体实现设计由助手整理。本轮仅维护需求记录，未删除实际数据或改产品代码。

- **两处辅助节点均推荐主工序（2026-11-04最新确认）**：用户明确“都推荐主吧”，适用于当前讨论的去毛刺第2次与清洗第3次；采用推荐后固定安排、保留各自原位置，不追加Bool、条件或关联来源追问。替代上一轮助手“去毛刺Bool/清洗主工序”提案，真实覆盖率18/20、19/20保持。R-09关闭，当前项目推荐内容补齐，接入设计和验证由助手整理，Execution仍deferred。

- **项目推荐口径集中收敛（2026-11-04最新批注）**：磨外圆、磨端面、磨槽、磨孔均推荐IT7及更高精度；珩孔、研孔、研外圆暂定IT6及更高精度。研顶尖孔归定位辅助类、Bool为用户倾向的暂定推荐；硬质阳极化、镀铜、标记推荐Bool，除铜跟随当前镀铜节点且保留原位置。去应力按材料牌号9Cr18，与当前淬火推荐一致。铣扁、钻孔、钻铰孔、铣槽、打孔、割型孔、割扁、打型孔统一推荐周边，特征子集由助手按用户授权选择，详表见[推荐清单](step3-recommendation-gaps-review.md)。两处辅助节点已由后续确认收敛为均推荐主工序，原助手去毛刺Bool建议保留为被替代历史。推荐、用户倾向及助手建议分别标记；不覆盖第四步现有规则，Execution仍deferred。

- **推荐答案补齐讨论恢复（2026-11-04，最新用户要求）**：用户愿意补充仍未知的工序推荐依据，目标为第三步一键采用能走完必答路径。PM-011据此恢复推荐答案补齐范围，替代此前全面排除讨论的处置，撤回历史保留。已只读核对41个母路线节点和保存记录，9个全覆盖、4个直接固定、1个已定Bool、4个有材料底稿不从头询问；其余23节点集中为[9项补齐清单](step3-recommendation-gaps-review.md)。保存状态、助手建议、模板参考与本轮确认分开记录，不启动产品实施或数据库修改。

- **当前项目方位新增“中间”（2026-11-04，用户明确）**：当前选项为A侧、B侧、中间、周边、所有方位，仍单选；先特征后方位、两条三元组全部满足及“所有方位”任一命中的含义不变。旧四项完整值域由此替代。已同步当前问题树、三元组表及PM-002/PM-003/PM-010，Execution仍deferred。
- **路线模板库资料参考（2026-11-04）**：用户提供`13-工艺路线模板库.md`并提出可据此确定工序推荐回答。资料适用性及不足见[参考笔记](route-template-reference-notes.md)，由PM-010保留为第三步配置参考；不直接采纳全部模板阈值或复杂分支。资料读取当时未改变PM-011撤回状态，最新已按用户重新提出的请求恢复推荐补齐讨论，不修改产品代码。
- **第三步回答是第四步初始规则的依据（2026-11-04，用户明确）**：第三步根据用户实际回答生成工序规则，第四步直接承接、审核和修改这些规则。全覆盖仍按既定决定直接进入主路线。推荐内容在用户采用前仅是建议；用户一键采用后应走与普通回答一致的规则生成过程。第四步人工修改不得被旧问答或后续提示词改动自动覆盖。此为业务依赖确认，具体保存和读取方式留待统一实施设计，Execution仍deferred，见PM-002。
- **第三步提示词配置及 PM-011 撤回边界（2026-11-04，历史后有新请求）**：用户此前确认通用框架加项目可配置内容，用户维护特征映射、方位及提问/推荐说明，同时供模型提示词、页面候选和规则生成使用，PM-010继续有效。用户曾明确“这个PM-11先撤回，我弄错了”，当时已排除该项；现在重新提出推荐答案补齐，按本节最新恢复记录处理，旧确认、示例及撤回原因保留，不自动恢复全部旧方案。Execution仍deferred。
- **钻孔推荐示例及产生依据（撤回前历史）**：示例通孔/盲孔/A侧是假设值，非项目实际规则；其推荐来源分析随 PM-011 撤回停止，不再作为当前待讨论项。原始记录留在 PM-011。

- **同名重复检验按出现序号区分（2026-11-04，用户确认）**：沿用当前处理方式，在工序名称上增加出现次数，按路线顺序显示为“检验（第1次）”“检验（第2次）”等。每处继续沿用母路线节点、位置及独立规则；第三步回答和第四步规则对应到同一处。节点和规则的技术衔接留待实施设计。见[完整树第26节](operation-question-trees-review.md)、PM-002/PM-003，Execution仍deferred。

- **辅助工序已知位置直接沿用（2026-11-04，用户确认）**：用户以“可以”确认：位置已经明确的清洗、去毛刺、检验沿用母路线原有位置，第三步只确定什么情况下需要安排，不重复询问位置。各处同名辅助工序分别保留自身节点/位置，出现方式继续收敛为主工序、Bool、条件或关联；沿用位置不自动等于关联，也不要求紧邻某道加工。确认范围限位置已明确的节点，尚未解决的合并节点身份或不明确位置不由系统臆定；不据此批准跨阶段移动或整套阶段缺失回退机制。见[完整树第24节](operation-question-trees-review.md)，Execution仍deferred。

- **去毛刺、清洗、检验采用明确要求条件（2026-11-04，用户批注确认）**：去毛刺删除对象特征集合条件；检验删除常规/专项检验要求集合及任一/全部匹配分支。去毛刺、清洗、检验的条件因素分别简化为“当前部位是否有明确去毛刺/清洗/检验要求=是/否”；检验项目、方法和对象仍保留在工序内容或配置。三元组审核稿已升为v2.9、总表14条，问题树同步更新。旧M02、Y01/Y02集合决定及“未注明不等于无”的附加讨论由新结论替代。详见PM-002、PM-003及[当前因素审核稿](operation-condition-triples-review.md)，产品Execution仍deferred。

- **普通问答上游答案修改后的清理原则（2026-11-04，用户确认）**：只清除依赖被修改答案、因此失效的下游回答和派生条件；无关回答保留，新分支需要重新回答，规则草稿按当前有效答案更新，不额外弹确认框。用户进一步确认，依赖关系如何标识、失效状态如何呈现，留待统一实施设计时确定。该确认是设计阶段安排，不启动产品实施。见[PM-002](issues/02-question-rule-alignment.md)、[PM-003](issues/03-question-framework-and-wording.md)和[完整树第25节](operation-question-trees-review.md)。Execution仍deferred。

- **模板映射后移（2026-11-04，主流程、可选性、入口布局、核心格式、验证交互及完整母路线映射已确认）**：用户明确规则定稿不导出；第5步由用户调整参数生成路线，认为结果没问题后可从右上角导出规则包，不另设独立验证通过按钮。第4步规则审核有变化时，第5步必须使用变更后的规则，删除旧验证结果并重新生成，导出包绑定当前生成所用规则版本。用户已确认模板映射是可选操作：不需要映射的用户可直接导出并结束；需要的用户可在第5步底部选择“继续分组模板映射（可选）”，最后在该步骤导入分组模板，完成后通过一个按钮保存映射并生成、下载完整规则包，替代保存后另点更新的两步交互。最后映射完整母路线及可能分支，不限于某次验证生成的具体路线；映射范围不再列为待讨论。用户确认未映射/已映射包共用同一规则核心：映射版附加工步到模板分组/特征的绑定和版本信息，不改写规则表逻辑；两种包对其系统运行没有影响，无须运行时按映射状态分支。未导出规则版本、前面候选及内部保存策略由实施设计衔接，版本编号由系统处理。Execution 仍 deferred。

- **PM-008 工具栏布局（2026-11-04，用户已确认）**：移除独立“智能判定精度”按钮，在其原位置放置“恢复隐藏工步”总按钮；保留“智能推荐”，无隐藏工步时恢复按钮禁用。现有智能推荐流程会在映射推荐后补全缺失精度，因此用户接受移除仅批量判定精度的独立入口；各工序仍可手动设置精度。Execution 仍 deferred，产品代码未修改。详见[PM-008](issues/08-exclude-process-steps-from-template-mapping.md)。

- **PM-009 叶子分组豁免（2026-11-04，用户已确认）**：每个叶子分组提供豁免映射按钮，由用户逐个自行决定是否豁免；不提供父分组批量豁免。用户确认进度区分已映射、已豁免和待映射；豁免只解除所选叶子的映射完整性要求，不改变路线、规则或目标系统运行含义。更换新模板后清除原模板全部豁免，不继承到新模板；该项已由待讨论转为确认。原因输入是助手延伸建议，不新增为用户必填要求，存储及清理由助手整理简化设计。PM-007 已确认可以完全跳过映射，但当前发布代码仍依赖模板映射，统一实施时要处理该依赖。详见[PM-009](issues/09-waive-template-group-feature-mapping.md)；Execution 仍 deferred。

- **当前项目粗加工阶段必有（2026-11-04）**：用户针对“没有粗加工时检验是否保留”的问题明确“粗加工应该一定会存在”，当前项目按粗加工阶段必有处理，关闭本例粗加工整段缺失的假设分支。不等于铣槽、钻孔等每一道粗加工都固定安排，也不等于粗加工后的每处清洗、去毛刺、检验必做；各节点仍按本身出现规则判断。不从本项目假设推广为所有零件通用事实，不据此自动补工序或新增验证约束。见[完整树第23节](operation-question-trees-review.md)，Execution仍deferred。

- **槽型映射及“所有方位”命中规则（2026-11-04，用户确认）**：磨槽与车槽共用U形外环槽、U形内环槽、外环槽、内环槽；铣槽使用另外六类候选，挖槽、切槽等不自动套用。方位选择“所有方位”时，任一方位出现所选特征即可满足，不要求每个方位都有；特征与方位条件仍同时满足并绑定同一加工对象。问题树审核稿升为v2.2，条件三元组稿升为v3.1，当前仍为13条；见PM-002、PM-003及[特征映射](current-project-feature-mapping.md)。产品Execution仍deferred。

- **孔类候选更正（2026-11-04，用户最新确认）**：钻孔及其他孔/内孔加工都使用孔、孔(盲孔)、孔(通孔)、内圆柱面作为候选，由工艺师按当前零件勾选，可多选；工序名不预先排除候选。此前“钻孔只对应孔基本特征”的记录由此替代。
- **第三步问题树与三元组更新（2026-11-04）**：粗加工特征与方位各一条三元组，先选特征再选一个方位，两条件均满足且绑定同一对象；铣扁按已定框架，不再单列平面/扁位待审。珩孔、磨端面沿用磨外圆问法；B-01铬酸阳极化为人工Bool例子。辅助工序四种安排方向已确认，下一步逐节点归类。J03及PDF提取核查不列入当前审核。问题树v2.5、三元组v3.3，当前条件项13条；PM-002/PM-003仍deferred。
- **粗加工问答与三元组顺序已确认（2026-11-04）**：先问特征并立即生成特征三元组C01a，再问一个方位并立即生成方位三元组C01b；两条条件同时满足且绑定同一加工对象。用户不需要再次回答“如何形成三元组”。后续仅讨论C-03钻孔的技术接入、保存和路线验证校验，不改变问答流程，也不重复讨论辅助工序框架。

- **淬火推荐回答与分支保留（2026-11-04，用户澄清）**：用户明确：淬火问题树仍须包括硬度分支，只是推荐回答为“材料相关”。推荐不等于已确认答案，不据此删除/隐藏硬度选项、直接跳到材料追问或自动定稿；用户实际选择材料后问适用牌号，选择硬度后问硬度范围，后续分别形成相应条件。既有用户决定的Bool及其它四模式入口继续保留。此推荐范围限当前淬火讨论，不自动推广到所有热处理。见[完整树第21节](operation-question-trees-review.md)，Execution仍deferred。

- **材料习惯与硬度范围口径（2026-11-04）**：用户平时更多选择材料相关依据；不据此强制所有热处理按材料或默认选定牌号。若选择硬度范围作为出现条件，超出所设范围即不满足。对输入本身为区间的情况，按整个要求区间落在规则允许范围内表达，部分越界不能仅因相交而通过；具体上下限、硬度制及端点包含关系随实际规则确定，不采用讨论示例为项目阈值。范围不满足是有效判断结果，不等于未答完。见[完整树第20节](operation-question-trees-review.md)，辅助工序位置建议仍待讨论，Execution仍deferred。

- **上传格式收敛边界（2026-11-04）**：用户要求移除辅助参考资料，并明确“仅支持 PDF”只指工艺规程上传文档格式；后续路线归并、规则分析、模板映射、规则定稿和验证生成继续保留。随后以“可以”确认第一阶段支持有效文字/表格 PDF，纯图片扫描件暂不新增自动识别，对异常文件及无法读取页明确提示。用户本轮明确客户没有旧版本，因此 PM-006 不纳入客户历史非 PDF 主资料兼容迁移，相关开放项关闭。参考资料整链路撤除及已确认清理范围继续见 PM-005；规则包 JSON、模板 XML 等其他用途不因该上传限制被删除。Execution 仍 deferred。
- **历史辅助资料直接清除（2026-11-04）**：用户回答“先全部删除吧”，选择清除历史辅助参考资料的记录、在线内容及专属文件，不采纳助手此前归档保留建议。该清理范围限辅助参考资料，不扩大为工艺规程主文档或项目删除；PM-005 执行仍 deferred，实际清理等待统一实施。

- **特征任一命中与人工Bool已确认**：2026-11-04最新用户确认：同一工序多选特征表示所选特征中存在一个或多个即可，按“包含任一”形成条件，不再追问任一/全部；该特征条件仍须与同一工序/对象范围内的方位等其他条件全部满足。淬火、渗氮等由用户决定本次是否安排的分支，在后续因素表转为Bool（是否安排该工序：是/否）；不把所有热处理统一改Bool，材料/硬度自动判断分支继续为条件。硬度区间和辅助节点位置本轮仅要求讨论，尚无新决定。详见[完整树第19节](operation-question-trees-review.md)。Execution仍deferred。

- **第三步全部完成后才能进入规则审核（2026-11-04，用户已确认）**：不设置“暂时答不出／待补充后跳过”入口；适用的必答问题及必要规则信息须在第三步回答完整，才能进入第四步规则审核。缺项仅按必填校验处理，不能算完成、不能留到第四步补齐，也不能自动当作无或Bool。全覆盖仍直接主路线，已确认信息复用，“其它”完整保存仍结束本工序。退出“其它”规则设置页且不保存、返回原问题已确认；草稿处理和辅助节点绑定仍待讨论，见第25节，Execution仍deferred。

- **本工序因素粒度与问答顺序已确认（2026-11-04）**：用户明确每道当前工序为同一方位的多个特征，特征多选、方位一个、适用精度暂时共用一个，并认可先特征后方位。范围限本工序，不要求逐特征分别填方位/精度，不扩大为全项目同值；特征多选后续已确认按包含任一，不再询问任一/全部，见第19节。替代助手上一轮逐特征不同方位输入建议，保留历史和原因；见[完整树第16节](operation-question-trees-review.md)。当时人工Bool用语仅作澄清，后续已确认直接由用户决定的分支转Bool，见第19节；退出“其它”设置页且不保存、返回原问题已确认，内部草稿细节和辅助工序位置仍待讨论，未完成出口以第17节最新确认为准，Execution仍deferred。
- **特征与方位的表达澄清（2026-11-04）**：用户进一步提出特征和方位分别一条三元组、全部满足；该方式可行，作为最新讨论方案记录。助手此前限定方位进字段名的建议保留为历史；两条均判断同一特征，避免跨对象各满足一条。界面无需据此固定新增两轮提问，字段/对象绑定/实际值仍待设计，详见[完整树第13节](operation-question-trees-review.md)，Execution仍deferred。
- **本轮批注方向（2026-11-04，细节待讨论）**：用户提出粗加工从“特征＋加工方位”入手，轴套类考虑A侧/B侧/周边，扩展此前只按特征的范围；建议将方位限定到同一特征对象，沿三元组表达，具体定义/值域/绑定未定。用户认为淬火明确要求偏人工Bool，并询问渗氮因素能否用Bool；记为倾向及待讨论，不标成全类转换已确认。见[完整树第12节](operation-question-trees-review.md)；产品Execution仍deferred。
- **完整问题树改为成组审核（2026-11-04）**：用户要求每个阶段的不同类型工序各取2～3个生成完整树；本轮按已确认七类各取3个，共21例，建立[完整问答树审核稿v1](operation-question-trees-review.md)，含原文位置、全部分支、共用其它设置、规则结果及结束/缺项校验（早期待补出口已由第17节替代）。该要求替代继续只审单句首问的安排；新增问句、选项、实际取值及实例模式仍待审核，既有确认不重问，Execution仍deferred。
- **粗加工铣槽问句已确认（2026-11-04）**：用户认可“这道铣槽，零件上有哪类槽时需要安排？”。按当前加工对象提供映射内候选及既有“其它”入口；不重复加入本项目已排除的粗加工因素。具体所选槽型和组合关系未据此批准，Execution仍deferred。
- **精加工问法已确认（2026-11-04，后续范围更新）**：磨外圆问“主要是为了满足哪方面的要求？”，珩孔、磨端面沿用该结构；当前因素仅问尺寸精度或表面粗糙度，J03形位公差分支已按后续批注移出当前审核范围。特征默认存在，具体阈值和组合交互仍待定，Execution仍deferred。
- **本项目因素范围（2026-11-04最新批注后）**：粗加工C01a特征＋C01b方位，方位值含A侧、B侧、周边、所有方位；选择所有方位时任一方位命中即可。孔/内孔加工含钻孔的四项候选由用户勾选；车槽/磨槽共用四类槽型，铣槽用另外六类。精加工当前仅J01尺寸精度、J02粗糙度，特征默认存在；J03形位公差及其PDF提取核查不在当前审核范围。热处理R01/R02/R03、表面处理B01～B03、去毛刺M01、清洗Q01、检验Y01及检验角色/位置配置保持。材料牌号、IT等级、Ra提供手动补录入口。详情见[审核稿v3.3](operation-condition-triples-review.md)，执行仍deferred。
- **特征来源与候选分开（用户已澄清用途）**：本项目实际特征类别来自20份工艺文件，`FeatureTemplate.xml`属于另一个产品的CAD字典，不能拿它反推本项目事实。用户本轮进一步明确，可以人工规定每类基本特征对应哪些CAD字典候选，作为第三步问题生成的提示词参考。此前“排除CAD字典”限定的是事实来源误用，不应扩大为禁止本轮明确提出的候选映射；见[实际来源](current-project-feature-inventory.md)与[映射草案](current-project-feature-mapping.md)。完整对应、提示词及接入方式待定，执行仍 deferred。
- **CAD候选集合补充原则（用户确认）**：本项目类别在另一产品CAD字典无对应项时，使用本项目自己的特征名称补入候选集合；型孔明确名为“型孔”，顶尖孔、锥面、球面保留本项目名。螺纹底孔作为本项目独立特征名，不映射为孔、通孔或盲孔。此处只定义候选特征表示，不推断具体几何；讨论稿已更新，尚未写入产品实际字典/提示词，Execution仍deferred。
- **全样本覆盖直接进入主路线**：用户明确认可此业务规则，后续改版予以保留；无需增加“全覆盖是否为主路线”的重复提问。
- **第三步初始分类的覆盖边界（已更新）**：全覆盖继续直接主路线；非全覆盖也允许用户明确设为主工序、以后固定安排。样本覆盖率是历史事实，不限制用户的最终安排方式。旧决定“非全覆盖只在条件、关联、Bool 三种中判断”已被本轮批注替代，原因是用户明确指出非全覆盖仍可被设为主工序；旧讨论保留为历史，详见 PM-002。
- **第三步形成初始分析，规则修改承担日常调整**：用户进入规则定稿后，修改集中在规则修改入口，避免两处反复同步。
- **锁定节点按页面含义识别**：用户所说“第四步规则修改”指 `/finalize` 规则定稿页。完整版中 `/template-mapping` 是模板映射页，不作为本次锁定触发点；基础版规则定稿才显示为第四步。
- **现有四模式作为对齐基线**：主工序、Bool 工序、条件工序、关联工序。当前条件模式为全部满足，关联模式为单来源自动带出并排在其后。本轮讨论没有批准新增 OR、嵌套组合或混合控制模式。
- **当前阳极氧化示例归 Bool**：用户明确“看图纸，注明阳极氧化就安排”由用户自行决定；本例采用用户直接选择是否安排的 Bool，替代助手此前直接归条件的建议。不推广为所有表面处理的默认模式，详见 PM-002、PM-003。
- **专业表述与少量提问**：用户认为先前示例问题过多、措辞过于 AI 化；要求贴近工艺师语言。具体题数、模板和措辞尚未定稿。
- **按工序类型区别提问**：用户早先认可热处理、机械加工、表面处理、检验、辅助工序五类及其关注方向；本轮明确检验归辅助类并可重复，更新为保留检验子类的专业问法。旧五类并列方式保留为历史，类内细分、具体题目及选择/补充顺序继续讨论，最终仍收敛到既有出现方式。
- **辅助检验可重复且与阶段位置有关**：用户明确同一路线可在不同阶段后重复安排检验，包括粗加工后、转入精加工及最后结束等场景；并未确认每个阶段都必须检验。各位置的安排方式、重复节点识别及阶段边界到实际工序的对应由 PM-002、PM-003 继续讨论，不擅自扩展单来源关联契约。
- **清洗、去毛刺与检验的安排思路相近**：用户明确两者“也是跟检验差不多”。按辅助类共性继续讨论服务的工序/阶段及当前节点的安排方式；共用具体问法为助手建议，尚未据此确认任何节点必做、关联或自动重复。
- **先逐类定问法与类型**：用户本轮要求先确定各类工序的提问方式和对应类型，再整理完整问题树；具体首问及回答归类表由 PM-002、PM-003 联合讨论，不将助手草案直接记为已批准需求。
- **保留专业提问，在早期回答中分流**：保留现有专业问题、样本候选及逐层细化能力；配置时明确以后固定安排可为主工序，希望每次生成时勾选是否安排为 Bool，系统条件判断继续相关技术追问，单来源必然带出只补来源。具体逐类问句、识别/补问细节、草稿结构及保存时机仍待定稿，当前执行授权不变。
- **其它入口完整保存即结束当前工序**：非全覆盖提问提供“其它”自行设置出现规则的入口，用户完整设置并保存后结束该工序问答、进入下一道。核心流程已确认；退出该设置页且不保存并返回原问题也已确认，未保存编辑如何处理、具体字段和草稿衔接细节继续见 PM-002、PM-003，执行继续 deferred。
- **精度分项追问并形成三元组**：用户已确认所选尺寸精度/表面粗糙度分别追问尺寸精度等级/粗糙度等级，资料作为参考候选由工艺师选定后形成条件；比较关系直接放进专业选项，让工艺师一次表达清楚，回答收敛为字段、运算符、值供第四步复用。具体选项文案、字段、等级、比较边界及保存细节仍见 PM-002、PM-003，执行继续 deferred。
- **按提问方向构建三元组模板**：用户明确其关注的是材料、特征、精度等方向的通用三元组构建，再据此组织各类工序的问题树。具体字段、允许关系、值域/候选来源及工序适用目录继续定稿；不再以单道调质的实际值填写代替该层设计。
- **影响因素范围保持开放**：用户进一步明确还有其他影响因素，材料、特征、精度仅为示例，不能将方向目录写死为这几项。PM-002 已记录毛坯、状态、性能要求、工艺衔接、生产资源等扩展候选，具体分类与字段仍是助手草案，不据此扩大执行模式或逐项强制提问。
- **材料牌号作为材料方向的明确例子**：此前已明确当前调质材料条件按牌号表达。用户“一个”曾被助手解释为单牌号确认；本轮用户指出未表达其意图，已将该单值表达保留为历史例子，不据此冻结问题树单选策略。具体目录和实际牌号未据此获批。
- **通用性**：用户要求考虑通用型，不能只围绕个别工序或演示材料设计。具体因素目录与范围仍待讨论。
- **示例不作业务数据**：此前“10 份样本、6 份磨外圆、Ra≤0.8μm”等均为讨论示例，不是当前真实项目统计或通用加工阈值。
- **目标运行环境**：保持项目 Win7 Pro 及现有运行时兼容要求；开发机验证不能替代 Win7 实机验收。
- **已有工作区**：保留当前未提交改动，后续实施只修改授权范围，不自动提交、推送、打包或发布。

## 统一实施准备

### 第二轮PM-014～PM-023（当前）

- [统一设计草案](../../docs/superpowers/specs/2026-11-05-system-improvements-round2-design.md)为draft-for-review，尚未由用户整体审核；独立审阅不等于用户批准。
- 建议R2-0先收敛设计及典型界面规范，R2-1第三步与共用条件，R2-2审核与验证，R2-3映射操作，R2-4补齐全系统视觉与联合验收。视觉规范贯穿各阶段，详见设计第8节。
- 当前只维护需求及方案文档；正式实施计划待整体设计认可后编写。最新用户确认后为9项ready-for-agent、PM-016一项needs-info，Execution全部deferred，不沿用上一轮五批的代码授权。

### 第一轮实施准备历史（已实施，保留原讨论）

以下为第一轮启动前的排期记录；其后已获五批明确授权并完成验收，当前结果以本总账首部和最终验收记录为准。下文“未获授权”“仍deferred”等保留当时语境，不用于判断第二轮授权。

当时没有获得明确启动授权的实施批次。PM-004 的旧授权记录已更正，已有候选代码和测试结果保留供审阅。

2026-11-04应用户要求完成[实施顺序评估](implementation-order-assessment.md)，按要求加入PM-004后，用户以“这样安排可以”确认以下五批顺序；不构成产品代码实施授权，各工单Execution仍deferred：

| 已确认顺序 | 工单 | 批次目标与依赖 |
| --- | --- | --- |
| 第一批 | PM-005、PM-006 | 收敛资料入口：移除辅助参考资料、仅允许PDF工艺规程上传；先理清后续资料来源 |
| 第二批 | PM-004 | 第二步并发解析、缓存复用及减少重复解析；在稳定PDF输入范围上独立验证耗时、结果一致性及目标环境兼容 |
| 第三批 | PM-001、PM-002、PM-003、PM-010 | 联合落实项目配置、专业问答、回答到规则输出及定稿后的只读保护；业务分支已收敛，具体措辞与数据衔接由助手纳入正式设计 |
| 第四批 | PM-007 | 以稳定规则为基础，落实先验证后导出、末尾可选映射、一键保存映射并导出；前后端进度与失效链路一起调整 |
| 第五批 | PM-008、PM-009 | 在已设计的映射保存与导出边界上落实隐藏/恢复和逐叶子豁免，并完成联合验收 |

本次重整后的补充建议（非新增排期确认）：

| 工单 | 建议位置 | 依据与边界 |
| --- | --- | --- |
| PM-011 | 第三批，与PM-002/PM-003/PM-010一起 | 当前项目推荐内容已补齐，复用同一候选配置、问题树和规则输出设计；只针对本次恢复范围，不自动恢复撤回前整套适配方案 |
| PM-012 | 第四批，与PM-007一起 | 验证因素栏读取第四步当前规则，与旧结果清理、路线生成和导出一起验收；材料选择、精加工展示及布局均已确认 |

- 先统一设计跨批的节点、规则版本、验证及映射保存关系，再分批改产品。后两批接口边界需提前考虑，不等到最后才设计。
- 上述为已确认的推进顺序，不将所有项强行串行化：第一、二批期间可整理第三批审核；PM-001可独立先做保护逻辑，随第三批联合验收；PM-008/009可在共同保存约定稳定后分别推进。PM-004不是后续问答工作的硬前置。
- 原确认排期覆盖10项（PM-001～PM-010）；最新总账12项已全部列入本次排期评估，建议PM-011补第三批、PM-012补第四批，两个新增位置尚未由用户确认。纳入评估不等于全部已具备实施条件，也不等于获得产品实施授权。
- 开始实施时按用户授权创建正式批次，列明纳入/延后项、设计与计划链接、顺序及验收要求；各批回写实际结果，再做跨批联合验证。
- 历史说明：此前先提出“先冻结PM-001，再联合讨论PM-002/003”，后扩展为PM-004暂存时的四批评估；用户要求加入PM-004后形成五批建议，本轮已确认排序。旧决定及原因保留，不影响既有确认或PM-001可独立验收的性质。

## 当前开放问题

### 本轮收尾后的设计边界（2026-11-04）

- PM-002：已定框架和当前推荐不重复审核。R03/B02查自身明确要求已确认，B03自动镀铜已撤除；Ra起始阈值0.8 μm由助手按用户授权选定，可按工序修改。字段转换、保存、第四步及验证接入由助手负责，不将快捷控件及未选分支参数写成用户必答。
- PM-003：淬火首问、末段检验问法沿用已确认表达；其他问句及主动改选备用方式后的表达由助手按既定业务统一整理，非全部历史草案逐句通过。今后若新增改变判断含义的提议，再单列讨论。
- PM-012：左侧因素/右侧路线、左侧基本信息/加工因素/人工安排三块布局本轮已获“同意”，与材料选择及精加工对象展示一同进入正式设计准备。
- PM-011：当前推荐内容已经补齐，没有新的用户内容审核项；IT6暂定、研顶尖孔Bool倾向沿用。后续技术设计及一致性验证由助手承担，不将其写成等待用户再次确认。
- 本轮四项明确答复关闭上述待定业务；PM-002/PM-003/PM-012转ready-for-agent，PM-011恢复Scope保持。用户随后已授权12项按五批统一实施，状态见本文件“批次记录”。

### 当前盘点（2026-11-04，重整12项需求）

前轮PM-007最后一步导入模板、规则变化后删除旧验证结果及PM-009换模板清除旧豁免已确认。本轮进一步收尾PM-002/PM-003要求分支及Ra选值、PM-012布局，当前12项均就各自已确认业务或恢复范围具备设计条件（ready-for-agent）。这不等于所有历史候选逐项获批或产品已验收；已确认内容不重复提问。

候选与规则字段对齐、页面和节点绑定、规则版本保存、包的内部编号、兼容及性能验收等由助手依据既有决定先整理设计，不列为用户逐项必须回答的业务问题。第一、二批核心范围已经明确，按已授权批次推进。

PM-011推荐内容已补齐，R-09两处辅助节点均推荐主工序，不再列待讨论；按授权范围纳入第三批。PM-012按授权纳入第四批。下方细项保留历史核对线索，涉及已被后续决定关闭的内容，以最新工单及审核稿为准。

### 早期第三步收尾分组（历史；本轮已明确项不重开）

用户询问还剩多少问题、是否需要每项都回答。当前PM-002/PM-003的剩余事项归并为3组；这是便于收尾的工作分组，不是3个必须逐题回答的业务问题，也不是全部系统的工单数量。

1. **七类问题树整体审核**：助手先按最新确认整理已有21例，集中标出尚未确认的问句、选项、分支及确实未明确的业务含义，交用户整批审核。既有确认直接沿用；示例参数不要求用户此时逐个给出。
2. **候选与规则数据对齐**：工序类型、项目候选、条件字段/关系/值、第四步及验证输入的对应，由助手基于既有范围和机制整理方案。
3. **页面、绑定与兼容设计**：回答保存、依赖清理、重复节点、必填提示、规则状态展示及历史问答兼容，由助手依据已确认行为出设计。

后两组不再作为逐项用户问卷。若发现现有决定无法覆盖、且会改变工艺判断或用户数据处理的选择，助手集中列明冲突及建议再请用户决定。剩余内容未因此获批，Execution仍deferred。

### 各工单细项索引

- PM-007：已确认映射为可选操作，最后导入分组模板并映射完整母路线及其可能分支；第5步右上角导出规则包，底部保留“返回规则定稿”并提供“继续分组模板映射（可选）”。第4步规则变化后删除旧验证结果，第5步使用新规则重新生成。模板时机、映射范围和旧结果呈现的业务选择已关闭；候选接入、可验证规则版本与正式包的解耦及内部保存策略由助手设计。映射清单内工步的人工排除见PM-008；无匹配特征的分组豁免见PM-009。当前代码要求模板输出才能发布完整版包，实施时需解除该依赖。
- PM-009：逐叶子按钮、用户自主豁免及更换新模板后清除原模板全部豁免已确认；具体保存与清理由助手设计。原因输入不新增为用户必填要求，不再把更换模板时是否保留旧豁免列为待讨论。
- PM-007 保存与导出合并已确认：映射完成后，一个按钮保存映射并生成、下载包含本次映射的完整规则包，替代“保存后另点更新”；只补充映射时沿用已验证规则核心和完整母路线，版本编号由系统处理。助手建议按钮文案为“保存映射并导出规则包”。内部保存策略留待实施设计，不据此覆盖或删除旧包；此交互不再列为待讨论。详见该工单。

- PM-002/PM-003：路线验证的业务粒度已按用户澄清收敛为每工序特征多选、单方位、精度暂时共用一个，先特征后方位已确认；具体字段/发布/验证输入的接通、待审实例和实际值仍未全部定稿，不能将21例视为全量批准。见[完整树第16节](operation-question-trees-review.md)，尚无实施授权。
- PM-002/PM-003：先特征后方位顺序已确认，已知项不重复问、两个选择步骤都保留其它；具体问句和补缺交互继续细化。选择不限方位时仅保留特征条件为助手建议，未知不能默认不限；当前每工序只取一个具体方位，不再扩展多方位录入方案。
- PM-002/PM-003：特征多选包含任一、用户决定分支转Bool已确认；硬度超出范围不满足及区间整体落入已由后续收敛，见完整树第20节。A侧/B侧/周边固定定义、字段接通及辅助节点位置仍待收敛。字段间全部满足保持不变，不新增条件间OR、四元组或混合模式。
- PM-002/PM-003：[各类工序三元组审核稿v2](operation-condition-triples-review.md)已完成因素范围、粗加工铣槽问句及精加工首问/三个追问确认；本轮按用户要求转为[七类21例完整树](operation-question-trees-review.md)成组审核，调质复用已知材料依据，新增分支不视为已确认。具体取值、阶段落点及同名重复/不同方法被合并后的独立绑定仍待核定；硬度范围判定已由第20节收敛，实际上下限及端点仍由配置明确。标印/包装不新增进范围；主/Bool/关联不强制三元化。
- PM-002/PM-003：三类要求的[取值目录草案](requirement-value-catalog.md)已核对，配合类型3项，现有special.requirements预置7项；专项技术及检验交付仍需区分工艺名称、检验角色/方法/项目、流程位置和交付规范，不能把候选全部写成已实现的封闭枚举。
- PM-002/PM-003：已明确按材料、特征、精度等方向构建三元组模板，再组织问题树。待定的是完整模板目录、工序到方向/模板的对应、字段及取值域统一、项目候选与用户适用范围的衔接；本阶段不要求先填写某个实例的实际牌号。
- PM-001：已有项目缺少“曾进入规则定稿”的记录，升级后怎样识别锁定状态。
- PM-002：如何将现有问答直接变成四模式草稿，缺少条件值或来源工序时怎样在第三步定位并提示补齐；未完成不得进入规则审核已确认，不再作为开放问题。
- PM-002/PM-003：“非全覆盖提问增加其它，转入自行设置规则，完整保存后结束并进入下一道”已确认；退出设置页不保存并回原问题也已确认；退出后未保存编辑和返回答案状态、具体文案及共用草稿方式仍待设计定稿。
- PM-002/PM-003：用户确认从“其它”进入自设规则页后可以退出且不保存并返回原问题，“其它”选项不删除；退出时本次填写直接丢弃、不留临时草稿、不要求保存；并确认恢复进入前原题状态（未答仍未答，已有答案保持，保存通过后才提交“其它”）。随后确认普通问题答案修改时只清理依赖且失效的下游回答/条件，无关回答保留；依赖识别与页面呈现留待实施设计。详见[完整树第25节](operation-question-trees-review.md)。
- PM-002/PM-003：已知辅助工序位置沿用母路线、第三步仅问出现方式已由第24节确认；同名重复检验沿用当前方式、增加出现序号区分已由第26节确认。节点绑定及不明确位置的核定留待实施设计；各处是否固定安排仍由对应规则配置。当前项目粗加工阶段必有，不重开粗加工整段缺失假设，也不新增所有阶段缺失问卷。
- PM-003：哪些信息可以从样本可靠带出、哪些必须问；通用因素分类、各工序分支和最终措辞怎样收敛。

以上问题记录后逐项讨论，不要求用户现在一次回答。

## 批次记录

B001（2026-11-03，授权记录已撤销更正）：助手曾把“可以”解释为仅启动 PM-004，已经产生候选改动；依“先讨论、后统一实施”约定，更正为等待明确启动。已有候选改动暂留，PM-001～PM-004 均为 deferred。[范围与验收](issues/04-step2-parse-performance.md)、[候选实施计划](../../docs/superpowers/plans/2026-11-03-step2-parse-performance.md)。不自动回退、提交、推送、打包或发布。

## Comments

### 2026-11-05：第二轮统一设计草案与集中审核入口

- 用户要求继续后，汇总PM-014～PM-023的业务边界、依赖、设计建议与验收方向，形成独立设计文件；不把助手拟定的问答生成/版本、恢复位置和内部保存策略记为用户确认。
- 对新设计安排一次独立只读可实施性审阅；结果回写设计文档。关联工单记录对应设计位置，业务状态和Execution不变。
- 审阅发现三项已有业务边界的设计缺口，已补清问答定义冻结、推荐失效时人工回答、映射输出投影与核心校验衔接；原审阅者针对性复核确认原三项在设计层面解决。记录位于设计末尾，不当作产品或用户验收。
- 文档校验确认10项不漏、8项ready/2项needs-info、10项deferred及关联本地链接有效；未运行产品测试。
- 旧五批准备段明确标为第一轮历史，避免将其未授权旧语句或已完成授权混用于本轮。未开始产品修改、实际提示词更新、Figma、提交、推送、打包或发布。

### 2026-11-05：PM-022状态获确认，进入方案整理阶段

- 用户确认已映射禁用豁免、待映射可豁免、已豁免可取消的安排，PM-022转ready-for-agent，Execution继续deferred。
- 当前PM-015、017～023共8项ready-for-agent；PM-014、016仍需整理具体生效机制和视觉设计，不能宣称10项所有细节已确认或自动启动实施。
- 下一阶段建议统一整理设计、实施依赖及验收，已有业务不重问，技术设计建议与用户确认分开记录；本轮仅维护需求文档，10项Execution均为deferred。

### 2026-11-05：回到PM-022讨论已映射叶子的豁免边界

- 用户询问下一步，按顺序回到PM-022；已明确的行内按钮、置灰及取消恢复不重开确认。
- 当前实现对已映射且未豁免的叶子禁用豁免；助手建议沿用这一边界，仅就是否需允许直接豁免向用户收敛，具体提案记在独立工单，尚未确认。
- 本次仅维护讨论记录，未开始设计或产品实施；本轮10项Execution仍为deferred。

### 2026-11-05：PM-021获确认，新增PM-023工序内排序

- 用户确认删除与统一未映射恢复方案，PM-021转ready-for-agent，Execution继续deferred。
- 新增PM-023记录同一道工序内每个工步可上移/下移的直接请求；助手的保存导出和稳定映射身份等设计归纳在工单中单独标注。
- 本轮范围由9项扩展为10项PM-014～PM-023；PM-022既有行内豁免要求继续保留，历史9项统计不回溯改写。
- 本次仅更新需求文档，未修改产品、实际工步顺序或映射数据，10项Execution均为deferred。

### 2026-11-05：PM-019输入获确认，整理PM-020并接续PM-021

- 用户确认本项目IT5～IT10六项下拉单选及规则阈值提示；PM-019转ready-for-agent，历史范围方向和精确端点状态已区分收敛。
- PM-020按用户此前明确要求补齐顶部信息移除范围与验收，转ready-for-agent，不重复索要相同确认；当前进入PM-021。
- PM-021已补充沿用本次映射范围、删除后解除关联和总恢复后未映射的讨论方案，恢复方式尚待确认。
- 本轮仅维护需求记录，未改产品或数据、未调用Figma，九项Execution仍为deferred。

### 2026-11-05：PM-018交互获确认，接续PM-019

- 用户确认顶部“确认全部规则”位置和批量操作方式；PM-018转ready-for-agent，Execution继续deferred。
- 当前按顺序返回PM-019，提出本项目IT5～IT10六项单选及显示当前规则阈值的具体方案供讨论；该方案未获最终确认，范围方向与精确端点的状态保持区分。
- 本轮仅维护需求文档，未实际确认规则、修改产品或开始设计工具操作，九项Execution均为deferred。

### 2026-11-05：PM-017展示获确认，接续PM-018

- 用户确认钻孔三元组展示；PM-017按已确认清单与呈现方式整理验收依据，Status转ready-for-agent，Execution继续deferred。
- 下一项进入PM-018，具体批量确认交互为助手待审提案，尚未获用户确认；详细范围和行为记在独立工单。
- 本轮仅更新需求文档，未开始产品实施、实际确认规则或调用Figma。

### 2026-11-05：PM-017呈现方式获确认，补充钻孔实例

- 用户确认上一轮条件清单贯通及常用条件优先、可展开本项目全部条件的方案，要求用钻孔展示具体三元组。
- PM-017新增两行条件文本示例，沿用既有推荐子集与周边方位，区分已确认框架、可选候选及本例选值；未将展示当作实际规则采用或具体界面验收。
- 仅更新需求工单和总账，未修改产品或实际规则，九项Execution仍为deferred。

### 2026-11-05：PM-016方向获确认，继续PM-017

- 用户确认浅色、简洁、紧凑的全系统视觉方向，统一控件与提示，并先由三个典型界面建立共用样式；PM-016的Decision更新为visual-direction-confirmed-design-pending，具体设计尚待整理。
- 当前进入PM-017，既有12条三元组不重开审核。基础字段表的静态核对线索和共用清单、常用条件优先且可展开全部条件的助手方案记在独立工单，方案尚待用户确认。
- 本轮只更新需求文档；未启动Figma、修改产品或执行产品测试，九项Execution仍为deferred。

### 2026-11-05：纠正精度范围理解及讨论跳项

- 用户说明精度输入应限制在IT5～IT10这样的实际范围，同时追问为何不讨论需求16、17。
- 助手承认将完整标准目录当作本项目输入范围，并跳过了16、17；恢复先PM-016、后PM-017，PM-019澄清先记录后续再收敛。
- PM-019将5～10记为用户提出的范围方向，准确端点尚未最终确认；旧完整目录提案保留并标为被纠正，未写成标准不存在IT0/IT01的事实。
- PM-016记录浅色、简洁、紧凑及典型页面先确定统一样式的助手建议；PM-017继续依据有效三元组，均未记作已收敛。全部Execution仍为deferred。

### 2026-11-05：提示词改为文件维护，不向用户展示

- 用户针对“问答提示词”批注明确“我还是觉得把它放在项目的提示词文件里，不想暴露给用户看”。
- PM-014当前有效范围改为项目文件维护，撤回此前面向用户的入口、页签、编辑区及关联设置改名方案；保留此前确认和替代理由，未回退产品工作区改动。
- 同步PM-015文件指导方式和PM-016当前视觉范围；全系统其他界面的Figma设计及浏览器验证安排继续沿用。
- 本轮仍共9项，Execution保持deferred；仅维护需求文档，未修改实际提示词、产品代码或启动设计工具。

### 2026-11-05：本轮走查需求收集基本完成

- 用户表示“以上基本就是我这次所验证之后的所有需求了”，本轮从持续收集转为基本收尾，范围为PM-014～PM-022，共9项。
- PM-016覆盖全系统视觉统一及后补的顶部提示条；其他8项继续分别维护目标和开放问题，未合并或遗漏。
- 后续按既定约定集中讨论方案，再统一实施；已确认的业务和三元组基线直接沿用，具体未定细节按各工单记录处理。
- 本次仅更新收集阶段状态；全部工单Execution仍为deferred，不据此升级决定状态、启动Figma设计或修改产品代码。

- 2026-11-04五条批注处理：已确认Ra≤阈值及淬火/末段检验两句问法，更新PM-002/PM-003和审核稿v2.8/v3.6；解释PM-012布局待审的左右双栏与左侧三块、处理要求多值匹配及镀铜保护备用条件范围。按工序自身要求判断是助手简化建议，尚未确认；镀铜仍推荐Bool。状态、Scope及Execution不变，仅更新讨论文档。

- 2026-11-04审核范围澄清：用户针对PM-002、PM-003的“少量待审”和PM-011的“推荐补齐”分别询问需审核什么。已在三张工单明确备用条件判断、问句表达及无新增推荐内容审核项三种边界；不重问已确认内容，技术设计由助手负责。本轮未新增业务决定或改产品代码。

- 2026-11-04重整12项需求及顺序：用户要求重新展示需求单及执行先后。已核对PM-001～PM-012，保留原10项已确认五批，建议PM-011恢复范围补第三批、PM-012补第四批，尚未将两个新增位置记为用户确认。PM-002/PM-003已成稿但少量问句/备选分支待审，PM-012整体布局待审；9项具备设计条件与3项待审分别列明。未新增编号或启动产品代码修改，Execution全部deferred。

- 2026-11-04 PM-007/PM-009业务收尾：用户批注明确分组模板最后导入，第4步修改后第5步使用新规则、删除旧验证结果，更换新模板则清除原豁免不保留。已更新两工单、总账及第四/五批验收边界；两项Status转ready-for-agent，Execution仍deferred。此前待定项及建议留在历史Comments，本轮未改产品代码或实际删除数据。

- 2026-11-04五批排序确认与剩余项盘点：用户明确“这样安排可以，现在还有哪个需求没有定清楚？”。已把PM-001～PM-010的五批顺序由助手建议改为用户已确认，PM-004确定单列第二批；三组业务收尾及助手负责的设计工作见当前开放问题。PM-011最新独立讨论记录保留，本次不自动纳入排期。仅更新总账、排序评估与PM-004工单，Execution均保持deferred，未修改产品代码。

- 2026-11-04 PM-004纳入排期：用户明确希望把PM-004加入整体方案。已同步工单及评估，建议放在资料入口收敛之后单列第二批，原第二至四批顺延。纳入范围已确认、第二批位置为助手建议，Execution保持deferred，未开始产品修改。

- 2026-11-04实施排序评估：用户要求评估需求先后顺序。已核对工单及资料、工作流、验证和模板保存调用，新增排期评估并在上方列出四批建议；PM-004保留、PM-011撤回。当前只形成建议和依赖说明，未启动产品修改，Execution均按原状态保留。

- PM-011 最新处置：用户明确“这个PM-11先撤回，我弄错了”。已停止本项及本轮模板库推荐回答分析，移出待讨论和实施范围；保留编号与旧决定，PM-010 独立需求继续有效。未改产品代码或删除系统已有功能。

### 2026-11-04：用户询问剩余数量与参与范围

- 助手将当前第三步剩余工作归并为问题树整体审核、候选与规则数据对齐、页面/绑定/兼容设计3组，提出先自行整理、集中提交审核，避免继续逐项询问实施细节。这是助手的收尾安排，不把用户询问视为问题树全部通过或产品实施授权。PM-002/PM-003同步，Execution仍deferred。

### 2026-11-04：重复检验增加出现次数

- 用户明确“跟当前的一样，可以加出现次数就行了”。按名称加路线出现序号区分各处检验，每处沿用母路线位置并独立保存回答/规则；更新PM-002、PM-003与完整树v1.18第26节。本次仅维护讨论记录，Execution仍deferred。

### 2026-11-04

- PM-002/PM-003 用户“可以”确认位置已明确的清洗、去毛刺、检验沿用母路线原有位置，第三步只确定出现方式，不再重复问位置。更新完整树v1.10第24节、K子树及三元组v2.7；原第23节待确认建议由此确认替代，合并节点身份和未知位置不自动补全。仅确认本方案，不是整树验收或产品实施授权，Execution仍deferred。

- 新增 PM-007：用户要求模板分组映射放到路线验证之后；核对现有导航、规则发布、快照生成和模板保存失效链路，记录先独立验证规则、最后映射完整母路线的助手建议。最终映射对象及验证完成语义仍待讨论，仅更新记录，Execution 继续 deferred。

- PM-002/PM-003：用户确认退出自设规则页且不保存、返回原题，不删除“其它”选项；退出时本次填写直接丢弃、不留临时草稿、不要求保存；并确认恢复进入前的原题答案状态。随后确认普通问题上游答案变更时只清理依赖且失效的下游回答和派生条件，无关回答保留；依赖标识与状态呈现留待实施设计。审核稿已更新至v1.17，仅维护讨论稿，Execution仍deferred。
- PM-007 用户曾提出模板映射可选的初步设想，后明确表示尚未决定；更新为待讨论，不再视为确认。路线验证满意后从右上角导出的交互已确认；映射必做/可选会决定首次导出是否受映射阻塞，需先完成利弊分析再冻结流程。
- PM-007 第5步按钮布局讨论：记录底栏双路径、右上角导出加底栏映射、重复导出入口三种方式；助手推荐保留右上角导出并在底栏提供可选映射，避免重复主操作。等待用户选择，不改代码。
- PM-007 包格式决定：用户认可共用同一规则核心，映射版额外带工步到模板分组/特征的绑定关系及模板/映射版本信息，映射不改变规则表逻辑；并明确有无映射对其系统运行没有影响，无需额外按状态分支。此前关于目标系统必须识别映射状态的前提为助手假设，已撤销。Execution 继续 deferred。
- PM-007 用户明确第5步调参生成路线，觉得结果没问题后从右上角导出规则包；不增加独立“确认验证通过”按钮。第4步规则审核变化后，第5步必须使用新规则；旧生成结果失效/刷新细节待设计。Execution 继续 deferred。
- PM-007 后续确认记录：映射可选；第5步右上角导出规则包，底部保留“返回规则定稿”并新增“继续分组模板映射（可选）”。本决定替代上方“可选性尚未确定”及“等待选择按钮布局”的历史待定状态；仅更新讨论记录，Execution 仍 deferred。
- PM-007 用户以“这个可以”确认更新包操作：保存映射后点击“更新规则包”，直接生成并下载含当前映射的完整规则包；仅补映射沿用已验证规则核心与完整母路线，版本编号交由系统处理。此前该交互的待确认建议已被本决定替代；内部旧包保留仍由实施设计提出。Execution 继续 deferred，本轮仅维护需求记录。
- PM-007 用户随后要求保存映射与导出合在一起，减少重复点击；现以一个按钮完成保存及完整规则包的生成、下载，替代上条“先保存、再更新”的两步交互。助手建议按钮文案为“保存映射并导出规则包”；该决定已同步工单当前范围和验收草案，Execution 继续 deferred。
- PM-008 用户确认工步操作是从本次映射待处理列表忽略，不改已验证路线；只有未映射工步可隐藏，已映射工步保持可见；总按钮一键恢复所有隐藏工步，恢复后作为未映射工步重新显示。核心行为已确认，Execution 仍 deferred。
- PM-009 用户确认分组豁免只作用于具体叶子分组，不提供父分组一键豁免。豁免状态保存、原因记录和模板版本变化时的处理仍待讨论；叶子范围属于用户决定，不是助手建议。Execution 继续 deferred。

- PM-002/PM-003 用户明确本项目粗加工阶段应该一定存在；关闭助手上一轮“没有粗加工时这处检验是否保留”的假设问题，保留其作为已排除的讨论历史。不把阶段必有扩为每道粗加工或所有辅助节点必做。已更新[完整树第23节](operation-question-trees-review.md)与两工单，沿母路线已有位置、只问出现方式仍为待讨论简化建议，Execution仍deferred。

- PM-002/PM-003 用户再次询问所有问题树是否完善。核对最新第19～21节：特征包含任一、人工选择Bool、硬度超出范围不满足、淬火材料推荐且保留硬度均已明确，不再作为开放业务问题。仍需讨论的重点是重复辅助工序的实际节点/位置及阶段缺失处理；七类21例尚有未审核措辞和选项，返回/取消、候选和字段映射等在设计时收敛。不能把状态询问视为21例整体验收或实施授权。见[完整树第22节](operation-question-trees-review.md)，Execution仍deferred。

- PM-002/PM-003 用户澄清“更多按材料判断”是淬火首问推荐“材料相关”，硬度仍须作为可选分支。修正此前仅记录使用习惯的不足；已在R-02标注推荐，并明确推荐不能当已确认依据跳过首问。更新完整树v1.9、三元组v2.6及两工单；硬度范围判定不变，Execution仍deferred。

- PM-002/PM-003 用户说明平时更多按材料判断；选择硬度条件后超出范围即不满足。已记录为整个输入要求在规则允许范围内、部分越界不满足，替代早期区间比较仍待讨论的记录。更新完整树v1.8、三元组v2.5及两工单；实际数值/端点未据此选定，辅助位置方案仍未批准。仅维护讨论记录，Execution仍deferred。

- 新增 PM-005/PM-006：用户提出完整删除辅助参考资料、上传仅支持 PDF；已确认其限制只针对上传格式，后续完整工作流保留。检查到当前界面仅隐藏参考面板，后台 CRUD、生成因素和资源加载仍有依赖；这些为设计依据。提出整链路清理与上传双端校验方向，旧数据和扫描件边界继续讨论，仅更新记录，PM-004 继续保留且暂不推进。
- PM-006：用户询问合适的支持边界；助手推荐第一阶段先沿用文字/表格提取，纯图片扫描件暂不新增 OCR，对无效内容和疑似遗漏页明确提示。已记为待确认建议，不承诺速度收益，Execution 仍 deferred。
- PM-006：用户随后以“可以”确认上述首期 PDF 支持边界，已移出当前开放问题；历史记录保留。PM-005 新增历史辅助资料归档备份、升级后退出业务读取的待确认建议。仅维护讨论文件，Execution 均仍 deferred。
- PM-006 本轮收尾：用户明确客户没有旧版本，不考虑客户历史非 PDF 工艺资料兼容迁移；该结论替代此前的历史兼容待定项。工单更新为 ready-for-agent，移出当前开放问题；Execution 继续 deferred，未启动产品实施。
- PM-005：用户选择“先全部删除吧”，确认辅助参考资料历史记录、在线内容及专属文件直接清除，不归档；此前归档建议保留为被替代历史。工单更新为 ready-for-agent / confirmed，Execution 仍 deferred，本轮仅更新记录，未实际删除数据或修改产品代码。

- PM-002/PM-003 根据用户四条批注，确认特征多选按包含任一，取消任一/全部追问；确认用户直接决定是否安排的分支在后续因素表形成Bool。已同步完整树v1.7与三元组v2.4；硬度区间用假设数值解释跨界歧义，重复辅助节点按出现方式和位置分别讨论，解释及建议尚非批准。旧待定记录和被替代建议保留为历史，Execution仍deferred。

- PM-002/PM-003 用户询问第三步问题树是否已全部理清。助手盘点：主框架、其它出口及完成门槛已明确，七类21例不等于全部分支已批准；关键未定项仍为条件判断口径（特征多选任一/全部、硬度区间等）、淬火/渗氮明确要求实例的Bool归类、重复辅助节点及位置处理。建议先讨论同一方位多个特征的触发含义；这是讨论顺序建议，不是新确认。取消返回、字段接通等继续在原工单内收敛，具体牌号/阈值由配置时选定，不要求现在填完所有实例。见[完整树第18节](operation-question-trees-review.md)，Execution仍deferred。

- PM-002/PM-003 用户否定“暂时答不出／标待补充后先看下一道”及“进入第四步后补齐”两项助手建议；确认不提供该跳过入口，第三步适用必答内容全部完成才可进入规则审核。已修订[完整树v1.6第17节](operation-question-trees-review.md)、共用校验及当前示例，旧建议保留为已否定历史。取消返回、辅助工序落点未据此批准；只更新讨论记录，Execution仍deferred。

- PM-002/PM-003 根据用户六条批注明确本工序因素粒度：特征多选、单方位、精度暂时共用一个，先问特征后问方位已确认；新增[完整树v1.5第16节](operation-question-trees-review.md)并更新[三元组v2.3](operation-condition-triples-review.md)。解释“人工选择”为验证/生成时直接选是否安排，未把澄清请求当作具体Bool批准；暂答不出/取消返回和重复辅助工序位置提出待讨论方案。当时未答完可否进入规则审核、同名节点具体绑定仍未定；前者已由后续用户批注否定，见第17节。保留被替代的逐特征不同方位建议及原因，Execution仍deferred。
- PM-002/PM-003 用户询问问题树框架是否都已确定；已在[完整树v1.4第15节](operation-question-trees-review.md)区分主干与五组未闭合项。保留用户此前“指路线验证”的澄清，核对现有验证页按规则包字段输入，提出特征/方位在同一记录内录入及判断的待审建议。没有把默认问答顺序、热处理Bool倾向、21例新问句或示例值升级为已确认，Execution仍deferred。
- PM-002/PM-003 用户提醒特征选择这一步也要保留“其它”；已在[完整树第14节](operation-question-trees-review.md)首问显式列出。选择后走既有四模式设置，完整保存结束本工序，不再接方位追问；候选缺项的补充入口与其它设置分开。此为既有规则的补全，不据此确认所有提问顺序细节，Execution仍deferred。
- PM-002/PM-003 用户询问先问特征还是先问方位。已在[完整树v1.3第14节](operation-question-trees-review.md)记录助手建议：默认先特征后方位，可靠已知项跳过；区分历史位置与通用触发范围，提问顺序不改变两条条件全部满足的规则。尚未把该顺序记为用户确认，Execution仍deferred。
- PM-002/PM-003 用户提出“特征一个、方位一个、都满足”的双三元组表达，已补入[完整树v1.2第13节](operation-question-trees-review.md)与[三元组v2.2](operation-condition-triples-review.md)。分析确认可沿既有全部满足组合，纠正助手此前把带方位字段作为首推的过窄表达；保留同一加工特征的判断范围，不声称现有执行器已支持或整个设计已获批准。只改讨论记录，Execution仍deferred。
- PM-002/PM-003 用户对21例批注：粗加工增加加工方位，轴套类考虑A侧/B侧/周边；淬火明确要求偏人工Bool，渗氮要求转因素也考虑Bool。已更新[完整树v1.1第12节](operation-question-trees-review.md)与[三元组v2.1](operation-condition-triples-review.md)，保留旧建议和重审原因。建议用方位限定的特征集合表达三元组，避免跨对象误匹配；区分布尔输入事实与Bool工序。方向和待定细节分别记录，未改产品代码，Execution仍deferred。
- PM-002/PM-003 用户要求每个阶段的不同类型工序各抽2～3个生成完整问答树供审核；已新增[21例审核稿](operation-question-trees-review.md)，七类各3个，记录原文位置和当前标准节点覆盖，区分全覆盖直接主路线、既有依据复用、专业条件追问及其它四模式出口。核对发现部分标准节点合有多个原文位置/检查方法，已记录绑定问题，未把合并覆盖当作每处/每种方法的独立覆盖率。全部新增问法、选项及数值仍待审，未改产品代码/数据库/正式字典/提示词，Execution仍deferred。
- PM-002/PM-003 用户“这个也可以”确认精加工首问及尺寸精度、粗糙度、形位公差三个按需追问；已替代上一轮待讨论状态。新增热处理问法草案，调质直接复用已知材料牌号依据，其余按硬度/明确要求补缺项；热处理问句仍待讨论，不据此选定牌号、阈值或启动实施，Execution仍deferred。
- PM-002/PM-003 用户“可以”确认上一轮粗加工铣槽的工艺师问法，已记入审核稿；本轮另拟磨外圆首问及尺寸精度、Ra、形位公差按需追问，后者仍为助手建议。未确认任何具体阈值、扩大组合模式或启动实施，Execution仍deferred。

### 2026-11-03

- PM-002/PM-003 根据用户8条批注确认并收敛本项目范围：C01；J01～J03且特征默认存在；R01～R03；B01～B03；M01/M02；Q01；Y01/Y02；检验角色/位置配置保留。用户明确这些是本项目因素。已将11条旧建议移至[审核稿v2历史表](operation-condition-triples-review.md)，保留原建议与替代原因；具体数值示例未转为业务阈值，下一步问法为助手建议，Execution仍deferred。
- PM-002/PM-003 用户要求按粗加工、精加工、热处理、表面处理、去毛刺、清洗、检验整理三元组和值供审核。已建立固定条目编号的[审核稿v1](operation-condition-triples-review.md)，补查项目材料/毛坯实际值，保留CAD目标候选与项目事实的区别；数值范围、扩展字段及辅助工序要求均标记待审，关联/位置另列。未修改产品代码、数据库或实际字典，Execution仍deferred。
- PM-002/PM-003 用户要求列出配合、专项技术及检验交付的所有值；新增[有来源的取值目录](requirement-value-catalog.md)，明确本地资料范围、系统7个预置标签与助手归纳候选的区别。记录不构成全量候选确认或产品实施授权，Execution仍deferred。
- PM-002/PM-003 延续因素目录汇总，修正映射提示词草案的冲突：允许正式CAD项及已登记的本项目补充项。螺纹底孔候选曾被表述为“孔/孔(盲孔)”或仅移除通孔，现按用户此前批注明确为本项目独立特征名，不映射为通孔或盲孔；旧表述均由本决定替代。本次仅文档修订，Execution仍deferred。
- PM-002/PM-003 根据用户对映射的批注修订：螺纹底孔候选移除孔(通孔)；型孔、顶尖孔、锥面、球面无对应字典项时分别保留为本项目自有特征项。并在条件组清单第七节归纳其它候选条件因素，材料、特征、精度/粗糙度之外含尺寸比例、公差、配合、状态/性能、专项要求、检验交付、毛坯余量、工艺衔接和资源/批量等。记录不构成全量业务规则确认或产品实施授权。
- PM-002/PM-003 新增[本项目基本特征→CAD候选映射草案](current-project-feature-mapping.md)：用户要求逐类规定候选并供第三步模型参考，已按13类整理，外圆/槽/倒角沿用用户示例，其余标作助手建议；型孔、顶尖孔、锥面、球面缺少明确字典项。仅建立讨论材料，未写入产品提示词或启动实施。
- PM-002/PM-003 根据用户纠正排除另一产品CAD字典，标记旧来源混淆；新增[当前项目实际特征清单](current-project-feature-inventory.md)，基于本地zyw项目20份文档、439条已提取明细列出13组有依据的类别。未逐页复核PDF，未把缺少细分名称写成不存在，执行仍 deferred。
- PM-002/PM-003 补充[从路线抽取具体加工对象的讨论](baseline-condition-groups.md)：记录原始工步与来源证据可复用能力、简化工步的限制、多对多对象对应和按需澄清的助手建议；对象粒度与抽取方案待定，继续 deferred。
- PM-002/PM-003 补充特征与项目对应的[核对清单第五节](baseline-condition-groups.md)：对照本体分类、项目特征字典、第三步关键词候选与规则人工分类，记录位置/对象绑定及数据来源的助手建议。具体映射和模板可用时机待设计，Execution继续deferred。
- PM-002/PM-003 新增 [本地基线条件组核对](baseline-condition-groups.md)：回答资料中已有何种分组条件，提供来源及三元化片段，区分原文明确条件、分类/指标候选与待核对项。资料研读未变为规则导入或产品实施授权，Execution仍为deferred。
- PM-002/PM-003 补充用户确认的开放范围：影响因素不限于材料、特征、精度。已记录可扩展目录与更多候选方向，保持具体分类待定，并区分出现条件、位置及参数作用，Execution 继续 deferred。
- PM-002/PM-003 根据用户纠正调整讨论层次：明确先按材料、特征、精度等提问方向构建通用三元组模板，再组织问题树。已新增跨方向草案，并更正此前把“一个”收窄成单选定稿的解释；具体模板目录待定，Execution 仍为 deferred。
- PM-002/PM-003 补充本例取值数量：用户回答“一个”，当前调质按单个材料牌号的等于条件收敛，实际牌号未给出；其它规则多值能力及 deferred 执行边界不变。
- PM-002/PM-003 更新局部确认：用户明确当前调质按材料牌号判断，已从该例开放问题中移除牌号/类别待定项；具体牌号、候选及整个条件目录仍待讨论，继续 deferred。
- PM-002/PM-003 补充三元组与问题树先后关系的讨论：已核对本体资料、标准条件字段和当前材料候选提取路径，记录先定字段及判断方式、项目提供实际候选、用户选定适用范围的助手建议；未把本轮疑问记成确认需求，继续 deferred。
- PM-003 补充用户意图澄清：本轮要讨论清洗实际会怎么问，上一轮数据绑定核对仅作背景。已记录清洗问句及按回答继续或结束的草案，PM-002 同步；具体问法仍待确认，继续 deferred。
- PM-002/PM-003 补充问题树绑定说明：现有问答按 `segment_id` 保存，规则配置指定 `process_id`；助手建议按类型复用模板、按当前节点保存实例、答案逐步补齐同一规则草稿并供第四步复用。同名重复工序独立绑定，具体技术设计仍待确认，Execution 继续 deferred。
- PM-002/PM-003 补充清洗、去毛刺讨论：用户明确与检验安排相近，已记录辅助类共性及共用问法建议；具体来源、位置和出现规则继续逐节点明确，执行仍为 deferred。
- PM-002/PM-003 确认“其它”核心流程：用户完整设置并保存后，结束当前工序问答并进入下一道；已更新原先待定状态，具体文案、取消返回和草稿衔接继续设计，仍为 deferred。
- PM-002/PM-003 新提案：用户希望各非全覆盖工序提问增加“其它”，选择后用类似规则修改的模块自行设置出现规则。已记录现状与助手建议（四模式、共用草稿、保存后结束及 PM-001 只读边界）；尚未确认具体流程或启动实施，继续 deferred。
- PM-002/PM-003 更新覆盖边界：用户批注明确，即使非全覆盖，也可以由用户设为主工序、变为固定安排。已将旧三模式限制标为被替代，区分历史覆盖统计、配置时固定安排与生成时人工勾选；具体入口待讨论，继续 deferred。
- PM-002/PM-003 记录用户“阶段结束就是最后，但也不一定是最后一个”的补充；“最后一个”的位置指代尚待澄清，不将检验固定绑定某个阶段末尾工序，继续 deferred。
- PM-002/PM-003 更新检验讨论：用户明确检验归辅助类，同一路线可在不同阶段后重复安排。已更新此前五类并列的分类归属，记录阶段位置与独立重复节点问题；是否固定检验及具体规则映射仍待确认，继续 deferred。
- PM-002/PM-003 确认比较关系直接进入精度回答选项，由系统组织条件三元组；已整理两条分支的问法草案，具体文案和数值不作已确认规则，继续 deferred。
- PM-002/PM-003 更新精度分支确认：用户认可参考候选，要求按所选项目分别问尺寸精度等级或粗糙度等级，并提出形成条件三元组。已记录分支与输出方向；具体阈值、比较关系及展示/保存细节继续讨论，不启动产品实施。
- PM-002/PM-003 补充磨外圆精度例子：用户明确精度较高时需要磨，并指出本体文件第七节已有样例；已核对参考表和现有精度分支。IT/Ra 参考值的采用、具体触发阈值及组合关系仍待确认，继续 deferred。
- PM-002/PM-003 更新调质例子：用户确认指定材料范围内必须安排调质，并明确归条件工序。材料触发关系和分类已确认，替代上一轮充分性及模式待定状态；具体材料范围尚未给出，不推广为所有热处理规则，继续 deferred。
- PM-002/PM-003 补充调质例子的用户回答：按材料判断。具体材料范围、是否为充分条件及最终模式仍待讨论；材料追问草案记录于 PM-003，不推广为所有热处理规则，继续 deferred。
- 用户对现有提问结合方案答复“可以”，PM-002/PM-003 已确认采用保留专业问题、早期分流的方向；之前的方案比较保留为历史，具体问法与规则草稿衔接仍待讨论，继续 deferred。
- 用户要求建立持续记录机制：“我们先讨论，然后后面统一实施”。已据此建立总账和独立工单。
- 用户提供 `/Users/zhaoyongwei/Desktop/本体与规则基线/` 作为第三步提问讨论的参考资料。已确认的覆盖分类边界记入 PM-002；资料适用性、提问建议与资料中的待核对内容分别记入 PM-002、PM-003，尚未批准导入为执行规则。
- PM-003 补充用户要求：按工序类型选择提问内容。此前“统一用一句通用开场”的助手建议已作历史说明；分类和具体问法继续讨论，尚未启动实施。
- PM-002/PM-003 本轮批注：五类基线已获认可，提问必须面向三种出现方式；“先选安排方式、再补对应信息”为助手新建议，尚未确认。历史中“类别清单未确认”已在对应工单补充本轮变更。
- PM-002/PM-003 表面处理讨论：已补充材料适用性、图纸/功能/部位要求，以及布尔输入字段与人工 Bool 工序的区别；优先评估条件模式是助手建议，尚未获用户确认。
- 表面处理现状补充：用户明确目前暂无“按某类材料、即使图纸未写也统一处理”的厂内规定；已据此收敛提问建议，不预设材料触发规则。具体首问、三种安排选项及默认模式仍待确认。
- PM-003 已记录“非全覆盖阳极氧化”的完整问题树草案，并与 PM-002 的条件、Bool、单来源关联输出对齐；仅补缺项、系统检查与待补充出口均供用户评审，尚未批准或实施。
- PM-002/PM-003 补充待讨论缺口：系统怎样知道哪些因素影响做不做。助手已更正不能先验排除材料等因素，提出以明确资料及工艺师说明/确认为依据；样本差异仅为线索，具体流程与结束标准未获确认。
- PM-002/PM-003 更新已确认决定：用户明确当前阳极氧化例子由用户自行决定，归 Bool；旧树中“按图纸直接归条件”已标注被替代。整体修订问法未定稿，仍等待统一实施。
- PM-002/PM-003 已按用户要求转为先逐类确定提问方式和类型；五类候选问法、回答归类及讨论顺序已记入 PM-003 供评审，尚未定稿或启动实施。
- 用户询问现有提问原则，PM-003 已补充当前代码调用链与模板核对，PM-002 同步现状：已具备按工序区别归因提问，尚非统一按 Bool/条件/关联组织首问；本次为现状记录，未启动产品实施。
- PM-002/PM-003 补充与现有提问结合的候选方案：保留专业模板、样本候选及记录链路；助手建议在各类首问/早期回答中尽早分流，只有条件分支继续细化相关技术因素。方案及具体问法未获确认，执行继续 deferred。
- 已回填本次讨论中的明确决定；问题树扩展、数值示例和助手建议未写成已批准功能。
- 对 PM-001 的确认来自用户提出置灰方案后，明确表示“我认为这个很合理”。
- 本次只建立记录与后续协作约定，没有修改产品代码、项目数据库或实际规则。
- PM-004 补充记录：上一轮助手已有候选代码改动，不能沿用上一条的“未修改产品代码”描述。本轮仅更正授权与验证状态；用户确认方向不等于明确启动实施，PM-004 恢复 deferred。未擅自回退混合工作区。
- PM-002/PM-003 用户确认普通问题答案修改后的失效分支处理：仅清理依赖且失效的下游回答和派生条件，无关回答保留，新分支重答、按当前有效答案更新规则草稿，不加额外确认弹窗。用户又确认依赖标识和失效状态展示留待统一实施设计时确定。已更新完整树v1.17及两项工单；本次确认设计安排，不启动实施，Execution仍deferred。
- PM-002/PM-003：已建立[第三步问题树v2.0集中审核稿](operation-question-trees-review-v2.md)，把七类21例及共用框架整理为单一当前审核入口，并列出5项集中审核点。旧v1.18稿保留为历史参考，不再作为当前审核版本；新增问句、候选和值仍待审。产品代码未修改，Execution仍deferred。
- PM-002/PM-003：用户查看问题树后大致认可并要求逐项查看三元组；当前因素审核稿已更新至v2.9第14节，列14条“字段/判断关系/值”。辅助工序最新口径已收敛为去毛刺、清洗、检验各自一个明确要求是/否条件，已删除集合匹配待审项；方位值域、精度比较和实际阈值仍待审核。仅更新讨论材料，产品Execution仍deferred。
- 特征映射纠正：螺纹底孔保留为本项目独立特征名，不映射为通孔或盲孔；已同步因素总表及映射稿，未变更产品字典或代码。
- PM-002/PM-003前几轮批注记录：车槽/铣槽候选拆分；材料、IT、Ra增加手动补录；方位值加入“所有方位”；J03形位公差暂移出当前有效因素。方位含义、磨槽映射及钻孔→孔已由后续决定确认，见上方跨项约束。核对06质量控制本体有形位公差分类及标准引用，但项目PDF提取符号、限值和基准的可靠性仍需验证。PDF硬度要求样例不作为规则阈值。当前审核稿为问题树v2.3、三元组v3.2/13条，Execution仍deferred。
- PM-002/PM-003本轮更正：上一条为v2.3/v3.2时的历史记录，钻孔单一“孔”候选及J03提取核查已由最新批注替代。现统一为问题树v2.5、三元组v3.3，共13条条件表达；粗加工先选特征再选方位，孔类四项由用户勾选；珩孔/磨端面问法、B-01人工Bool及辅助工序逐节点讨论方向已确认。下一项是各处辅助工序的具体出现方式；未将实例规则全量批准，Execution仍deferred。

### 2026-11-05：记录前轮四项批注的确认结论

- PM-012双栏及左侧三块布局确认；PM-002/PM-003按自身明确要求判断，撤除B03自动镀铜；用户授权助手选Ra起始阈值0.8 μm，可按工序修改。三项改为ready-for-agent，当前12项均就既定业务或恢复范围具备设计条件。
- 同步PM-010/PM-011、问题树v2.9、三元组v3.7及推荐清单v1.3；有效条件13→12条，旧决定及替代理由保留。未改产品代码、配置或数据库，全部Execution仍deferred。原五批顺序保持，PM-011/PM-012新增排期位置仍是建议。

## 2026-11-05：五批实施联合验收

全部十二项已按授权顺序实现。当前后端1703通过/110跳过、前端872通过、生产构建与Python3.8源码检查通过；临时项目已走通PDF→归并→问答→规则定稿→验证/直接导出→可选映射/隐藏恢复/叶子豁免/更新包。41节点真实前端规则输出通过后端编译和41个正向生成场景。上传区单列宽度修正归入PM-005。详细证据、待完成的独立审查及Win7/真实模型限制见[联合验收报告](../../docs/superpowers/reviews/2026-11-05-system-improvements-acceptance.md)。

## 2026-11-05 最终实施与验收关闭

十二张工单均已有独立Answer和验证边界，已按五批完成。上传主输入宽度问题归PM-005收尾，不另增需求编号。保存完整母路线、连续作答、辅助隐藏、扫描正文、批量/自动保存并发共五项审查发现均先复现后修复，独立复核未确认剩余重要缺陷。最终证据见[联合验收](../../docs/superpowers/reviews/2026-11-05-system-improvements-acceptance.md)、[原独立审查及修复复核](../../docs/superpowers/reviews/2026-11-05-independent-workflow-review.md)和[并发跟进](../../docs/superpowers/reviews/2026-11-05-autosave-batch-follow-up.md)。所有产品流程仍使用现有依赖；限制不因done状态消失，不宣称所有输入组合无缺陷。

## 第二轮round2-all实施授权（2026-11-05）

用户已明确启动PM-014～PM-023全部10项，授权替代此前deferred；当前按[正式实施计划](../../docs/superpowers/plans/2026-11-05-system-improvements-round2.md)连续实施。PM-016具体稿由已确认方向收敛，不再作为业务问题反复追问。保留此前讨论状态用于追溯，不沿用第一轮授权替代本次授权。


## 第二轮round2-all完成与用户自行验收（2026-11-05）

PM-014～PM-023共10张工单已各自补Answer并关闭。按文件指导/共用条件→批量确认及映射删排→统一视觉→联合验收的依赖完成；最终总审发现除铜分类与未引用冻结候选两条Important，已一次集中修复及唯一窄复核通过，含可信全覆盖直接主路线边界。完整后端1873通过/110跳过，前端973通过，生产构建通过；详细实际结果、执行裁定、Figma及环境限制见[第二轮验收](../../docs/superpowers/reviews/2026-11-05-system-improvements-round2-acceptance.md)。

用户已明确要求审查结束后清空重启。已备份`.runtime/db-backups/before-round2-manual-review-20261105-212014/`，副本清理旧项目/资料/规则/生成/映射全部业务记录，保留配置、提示词、预置及ID高水位；标准8000/5173服务启动，Chrome打开上传首页，初次空库及健康检查通过。交接后用户新建内容继续保留，不再次清空。无提交、推送、打包或发布。
