# wwsearch-reconstruction

面向工程团队 / AI Agent 工程 / 测试架构 / 需求重建 / 可复现研究的 Tencent/wwsearch 逆向需求工程与测试生成项目。

- 原始项目：Tencent/wwsearch（C++ 搜索引擎）
- 项目目标：使用 AI 对复杂 C++ 搜索引擎进行需求重建与测试生成
- 项目核心价值：从源码恢复规则与测试资产，建立 Rule ID / TS ID 的可追溯闭环

> README 生成时间（UTC）：`2026-05-11 07:54:46Z`

---

## 1. 项目背景

- 原始项目：Tencent/wwsearch
- 项目目标：在缺少完整 BRD 与测试资产的情况下，用 AI 辅助完成“需求重建 + 测试生成”
- 核心价值：将源码中的隐式行为重建为可追溯规则（Rule IDs）与可运行测试（TS IDs + unittest）

为什么：

- 传统系统常见问题：缺少系统化 BRD；规则散落在实现中；测试资产不足导致回归风险不可量化
- AI 的作用：加速静态阅读、调用链归纳、接口行为推断与规则抽取；但必须用证据与可复现运行约束，避免幻觉

---

## 2. 项目目标

### 阶段1：需求重建

包括：

- 架构分析 / API 分析
- Query 链路分析 / 写入链路分析
- 规则抽取与编号
  - BR-*：业务规则
  - CFG-*：配置/约束规则
  - CG-*：代码生成/工程生成规则
- 覆盖率分析（规则覆盖 / 场景覆盖 / 模块覆盖）

### 阶段2：测试生成

包括：

- 测试场景设计（TS-*）
- Python 集成测试生成（unittest）
- helper 封装
- 自动化运行
- expectedFailure 标记
- skip 策略（缺入口/缺证据时工程化降级）

---

## 3. 项目结构

```text
/work
├── docs/
│   ├── architecture_analysis.md
│   ├── business_rules_wwsearch.md
│   ├── rules_analysis.md
│   └── test_scenarios_wwsearch.md
├── tests/
│   ├── integration_test_wwsearch.py
│   └── wwsearch_helper.py
├── scripts/
│   └── env.sh
├── prompts/
│   ├── task1.md
│   └── task2.md
└── wwsearch/
    ├── include/
    ├── src/
    ├── example/
    ├── unittest/
    └── ...
```

重点目录：

- docs/：规则与场景文档
- tests/：Python 集成测试与 helper
- wwsearch/：上游 C++ 源码
- scripts/：环境脚本
- prompts/：阶段性 Prompt（用于复现/审计）

---

## 4. 需求重建方法论

- 静态分析：以 wwsearch/include 与 wwsearch/src 为主
- 调用链分析：从可执行入口回推 Query / Write 路径
- API 推断：Add/Update/Replace/Delete/Query 的输入、合并语义、错误边界
- 规则抽取：把关键行为/约束固化为 Rule ID（BR/CFG/CG）
- 可追溯性：规则必须能回指到源码证据路径或可运行测试输出

Rule ID 示例：CFG-01、CG-02。

---

## 5. 测试生成方法论

- 从规则与源码推断行为 → 结构化为 TS-* → 生成 unittest 测试方法
- expectedFailure：标记“已识别但仍缺证据/入口”的失败点
- skip：当缺少可脚本化入口（例如缺官方 CLI）或关键证据缺失时，必须 skip 并说明原因

为什么采用 subprocess + helper + 临时索引目录：

- subprocess：以黑盒方式驱动 C++ 可执行文件，减少 ABI/绑定复杂度
- helper：收敛 CLI 调用、输入构造、输出解析、临时目录管理
- 独立临时索引目录：保证幂等与可复现，避免状态污染

---

## 6. 覆盖率统计

> 所有数字均来自真实解析（文档/测试代码）+ 容器内实际测试运行输出；缺失则标记 UNKNOWN。

### 汇总统计

| 类型 | 数量 |
| ----------------- | --: |
| BR Rules          | 36 |
| CFG Rules         | 3 |
| CG Rules          | 2 |
| TS Scenarios      | 8 |
| Integration Tests | 7 |
| expectedFailure   | 2 |
| skipped           | 5 |

覆盖判定口径（可复现）：

- 规则覆盖率（在 TS 或测试代码中显式出现 ID）
  - BR：11/36
  - CFG：0/3
  - CG：0/2
- 测试覆盖率（场景落到测试）
  - TS：7/8

### 模块覆盖率（启发式）

| 模块 | 规则覆盖率 | 测试覆盖率 | 状态 |
| -- | -- | -- | -- |
| `include` | 3/11 | UNKNOWN | GAP |
| `src` | 8/30 | UNKNOWN | GAP |


### Python 行覆盖率

- coverage.py：UNKNOWN
- 结论：容器内未安装 coverage，无法生成 Python 行覆盖率报告，因此此项为 UNKNOWN。

### P0/P1/P2 缺口数量

- P0：UNKNOWN
- P1：UNKNOWN
- P2：UNKNOWN

---

## 7. 运行方式

### Docker 环境

所有命令必须通过：

```bash
sudo docker exec ww bash -lc "<command>"
```

所有路径基于：/work。

### 运行测试

```bash
sudo docker exec ww bash -lc "
cd /work &&
export LD_LIBRARY_PATH=/work/wwsearch/build/lib:$LD_LIBRARY_PATH &&
python3 tests/integration_test_wwsearch.py -v
"
```

本次实际运行输出（自动捕获）：

```text

mesg: ttyname failed: Inappropriate ioctl for device
test_add_document_success (__main__.WWSearchIntegrationTest) ... ok
test_add_duplicate_id_should_fail (__main__.WWSearchIntegrationTest) ... ok
test_add_or_update_document (__main__.WWSearchIntegrationTest) ... skipped 'No official CLI for AddOrUpdateDocuments; need helper executable or build wwsearch_ut with scriptable entry.'
test_delete_then_query_should_not_match (__main__.WWSearchIntegrationTest) ... skipped 'DeleteDocuments CLI missing; need helper executable or build wwsearch_ut with scriptable entry.'
test_query_multi_field_expected_failure (__main__.WWSearchIntegrationTest) ... skipped 'BR-Query-05 is UNKNOWN; repo lacks query-string parser/routing evidence and official executable entry.'
test_replace_document_should_not_merge_old_fields (__main__.WWSearchIntegrationTest) ... skipped 'ReplaceDocuments CLI missing; additionally BR-Replace-01 is PARTIAL and needs more evidence to assert full semantics.'
test_update_document_success_and_merge_old_field (__main__.WWSearchIntegrationTest) ... skipped 'No official CLI for UpdateDocuments; need helper executable or build wwsearch_ut with scriptable entry.'

----------------------------------------------------------------------
Ran 7 tests in 0.251s

OK (skipped=5)
```

---

## 8. 阶段2关键 Prompt（摘要）

- Prompt Strategy：只生成可被运行/可被解析的最小闭环资产；不确定处必须降级为 UNKNOWN 或 skip
- Agent Workflow：规则抽取（Rule IDs）→ 场景结构化（TS IDs）→ 测试生成与容器内运行 → 覆盖量化
- Docker Strategy：所有读取/统计/运行都在容器内执行
- Anti-Hallucination Strategy：统计必须来自解析脚本或测试输出；缺失必须写 UNKNOWN 并说明原因

---

## 9. 实现亮点

### AI 工程亮点

- 源码级规则抽取与证据可追溯
- Rule → Scenario → Test 映射与可量化覆盖
- expectedFailure/skip 工程化处理不确定性
- Docker Agent 执行模型保证复现

### 测试架构亮点

- 幂等测试（临时索引目录）
- subprocess 驱动（贴近真实使用）
- helper 封装（复用与一致性）
- ID 体系支持精确定位与资产审计

---

## 10. 当前不足（结合实际产物）

- 集成测试中多条用例被 skip：原因集中在缺少官方/可脚本化 CLI 入口（测试输出已记录）
- CFG/CG 尚未在 TS 或测试中形成显式引用，导致规则覆盖统计为 0（需要补齐映射）
- Python 行覆盖率无法统计：容器缺少 coverage 依赖

---

## 11. 高 ROI 后续方向

- 优先补齐可脚本化入口（或构建测试驱动可执行）：直接减少 skip、提升可验证覆盖
- 动态 tracing + 静态分析：把推断补成证据，提升规则可信度
- 自动生成 fuzz/property-based tests：覆盖 tokenizer 与 Query 组合边界
- Rule Diff + 增量重建：支持版本演进下的低成本持续重建与回归选择

---

## 12. 最终结论

本项目已建立可复现的需求重建 → 场景 → 测试闭环，并用容器内真实运行结果暴露关键工程阻塞点。下一步最高 ROI 是补齐可脚本化入口与 Rule ↔ TS ↔ Test 显式映射，从而把推断资产升级为可验证资产。
