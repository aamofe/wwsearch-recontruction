# wwsearch-reconstruction

Tencent/wwsearch 逆向需求工程与测试生成项目。

- 原始项目：Tencent/wwsearch（C++ 搜索引擎）
- 项目目标：使用 AI 对复杂 C++ 搜索引擎进行需求重建与测试生成
- 项目核心价值：从源码恢复规则与测试资产，建立 Rule ID / TS ID 的可追溯闭环

---

## 1. 项目背景

- 原始项目：Tencent/wwsearch
- 项目目标：在缺少完整 BRD 与测试资产的情况下，用 AI 辅助完成"需求重建 + 测试生成"
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
- C++ CLI helper 封装（补充官方示例缺失的写入操作入口）
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
│   ├── integration_test_wwsearch.py       # v1 原始版本（7个测试）
│   ├── integration_test_wwsearch_v2.py    # v2 扩展版本（28个测试）
│   ├── wwsearch_helper.py                 # v1 helper
│   └── wwsearch_helper_v2.py              # v2 helper（含 helper 程序封装）
├── scripts/
│   └── env.sh
├── prompts/
│   ├── task1.md
│   └── task2.md
└── wwsearch/
    ├── include/
    ├── src/
    ├── example/
    │   ├── example.cpp                    # 官方示例（Add + Query）
    │   └── wwsearch_test_helper.cpp       # 新增 CLI helper（Update/Delete/Replace/AddOrUpdate）
    ├── unittest/
    └── ...
```

重点目录：

- docs/：规则与场景文档
- tests/：Python 集成测试与 helper
- wwsearch/example/：官方示例 + 新增测试用 CLI helper
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
- expectedFailure：标记"已识别但仍缺证据/入口"的失败点
- skip：当缺少可脚本化入口或关键证据缺失时，必须 skip 并说明原因

为什么采用 subprocess + helper + 临时索引目录：

- subprocess：以黑盒方式驱动 C++ 可执行文件，减少 ABI/绑定复杂度
- helper：收敛 CLI 调用、输入构造、输出解析、临时目录管理
- 独立临时索引目录：保证幂等与可复现，避免状态污染

### CLI helper 设计（wwsearch_test_helper）

官方 `wwsearch_example` 仅覆盖 Add + Query，为补齐测试入口，新增 `wwsearch_test_helper` 可执行程序，支持以下操作：

```bash
wwsearch_test_helper <db_dir> add        <docid> <text> <f1> <f2>
wwsearch_test_helper <db_dir> update     <docid> <text> <f1> <f2>
wwsearch_test_helper <db_dir> addorupdate <docid> <text> <f1> <f2>
wwsearch_test_helper <db_dir> replace    <docid> <text> <f1> <f2>
wwsearch_test_helper <db_dir> delete     <docid>
wwsearch_test_helper <db_dir> query      <term> [field_id]
wwsearch_test_helper <db_dir> get        <docid>
```

输出格式为结构化文本（`RESULT:OK` / `RESULT:FAIL` / `QUERY:MATCH` 等），供 Python 解析。

---

## 6. 覆盖率统计

> 所有数字均来自真实解析（文档/测试代码）+ 容器内实际测试运行输出。

### 汇总统计


| 类型                | v1（原始） | v2（扩展后） |
| ----------------- | ------ | ------- |
| BR Rules          | 31     | 31      |
| CFG Rules         | 3      | 3       |
| CG Rules          | 2      | 2       |
| TS Scenarios      | 8      | 8       |
| Integration Tests | 7      | 28      |
| expectedFailure   | 2      | 1       |
| skipped           | 5      | 4       |


覆盖判定口径（可复现）：

- 规则覆盖率（在测试代码中显式出现 Rule ID 或对应行为被验证）
  - BR：v1 约 11/31 → v2 约 25/31
  - CFG：0/3（CFG-03 为 UNKNOWN，CFG-01/02 有行为覆盖但未显式引用 ID）
  - CG：0/2（行为已覆盖，未显式引用 ID）
- 测试覆盖率（场景落到测试）
  - TS：7/8（TS-ww-Query-02 因规则 UNKNOWN 保留 skip）

### 模块覆盖率（启发式）


| 模块        | 规则覆盖率                                   | 状态  |
| --------- | --------------------------------------- | --- |
| `include` | 提升（BR-Field/BR-Idx 已覆盖）                 | 改善  |
| `src`     | 提升（BR-Upd/BR-Del/BR-AoU/BR-Replace 已覆盖） | 改善  |


### Python 行覆盖率（coverage.py 6.2 实测）

```
Name                                    Stmts   Miss  Cover
-----------------------------------------------------------
tests/integration_test_wwsearch_v2.py     190      5    97%
tests/wwsearch_helper_v2.py                71      5    93%
-----------------------------------------------------------
TOTAL                                     261     10    96%
```

### P0/P1/P2 缺口数量

**P0（阻断正确性/一致性验证）**

- P0-1：BR-AoU-02 — AddOrUpdate 并发原子性/冲突解决：无锁/事务证据，需动态验证
- P0-2：BR-Partition-02 / BR-Query-05 — 跨分区路由：DoQuery 仅接受单 TableID，未见 fanout/merge 实现

**P1（功能可用但行为不完整）**

- P1-1：BR-Replace-01 — Replace 完整语义为 PARTIAL，仅证实跳过 MergeOldField
- P1-2：CFG-03 — 异步写队列 DbRocksWriteQueue：接口存在但实现无法在 repo 内证实

**P2（可用性/可维护性风险）**

- P2-1：store_buffer 协议风险（必须为 RocksDB WriteBatch bytes，否则注释提示 corruption）
- P2-2：ColumnFamily 枚举顺序兼容风险（注释要求不可变更顺序）

---

## 7. 运行方式

### Docker 环境

所有命令通过：

```bash
sudo docker exec ww bash -lc "<command>"
```

所有路径基于：`/work`。

### 编译（含 CLI helper）

```bash
sudo docker exec ww bash -c "cd /work/wwsearch/build && cmake .. && make -j4"
```

### 运行 v1 测试（原始版本）

```bash
sudo docker exec ww bash -lc "
cd /work &&
export LD_LIBRARY_PATH=/work/wwsearch/build/lib:\$LD_LIBRARY_PATH &&
python3 tests/integration_test_wwsearch.py -v
"
```

### 运行 v2 测试（扩展版本，推荐）

```bash
sudo docker exec ww bash -lc "
cd /work &&
export LD_LIBRARY_PATH=/work/wwsearch/build/lib:\$LD_LIBRARY_PATH &&
python3 tests/integration_test_wwsearch_v2.py -v
"
```

### 运行 v2 测试并生成覆盖率报告

```bash
sudo docker exec ww bash -lc "
cd /work &&
export LD_LIBRARY_PATH=/work/wwsearch/build/lib:\$LD_LIBRARY_PATH &&
python3 -m coverage run tests/integration_test_wwsearch_v2.py &&
python3 -m coverage report
"
```

### v2 实际运行输出

```text
test_add_docid_zero_should_fail (TestAdd) ... ok
test_add_document_success (TestAdd) ... ok
test_add_duplicate_id_should_fail (TestAdd) ... ok
test_add_then_get_fields (TestAdd) ... ok
test_add_then_query_hit (TestAdd) ... ok
test_addorupdate_idempotent (TestAddOrUpdate) ... ok
test_addorupdate_insert_when_not_exist (TestAddOrUpdate) ... ok
test_addorupdate_update_when_exist (TestAddOrUpdate) ... ok
test_delete_nonexistent_doc (TestDelete) ... ok
test_delete_then_get_not_found (TestDelete) ... ok
test_delete_then_query_no_match (TestDelete) ... ok
test_query_different_table_isolation (TestQuery) ... ok
test_query_empty_result_ok (TestQuery) ... ok
test_query_filter_sort_pagination_via_example (TestQuery) ... ok
test_query_multiple_docs_match (TestQuery) ... ok
test_query_suffix_match (TestQuery) ... ok
test_replace_new_term_queryable (TestReplace) ... ok
test_replace_nonexistent_doc (TestReplace) ... ok
test_replace_success (TestReplace) ... ok
test_addorupdate_concurrent_atomicity (TestUnknownRules) ... skipped 'BR-AoU-02 is UNKNOWN'
test_async_write_queue (TestUnknownRules) ... skipped 'CFG-03 is UNKNOWN'
test_cross_partition_routing (TestUnknownRules) ... skipped 'BR-Partition-02 is UNKNOWN'
test_query_multi_field_expected_failure (TestUnknownRules) ... skipped 'BR-Query-05 is UNKNOWN'
test_update_changes_query_result (TestUpdate) ... ok
test_update_existing_doc_success (TestUpdate) ... ok
test_update_merges_old_field (TestUpdate) ... ok
test_update_nonexistent_doc_should_fail (TestUpdate) ... ok
test_batch_fail_propagation_via_duplicate (TestWriteBatch) ... ok

----------------------------------------------------------------------
Ran 28 tests in 4.655s

OK (skipped=4)
```

---

## 8. 阶段2关键 Prompt（摘要）

- Prompt Strategy：只生成可被运行/可被解析的最小闭环资产；不确定处必须降级为 UNKNOWN 或 skip
- Agent Workflow：规则抽取（Rule IDs）→ 场景结构化（TS IDs）→ 测试生成与容器内运行 → 覆盖量化
- Docker Strategy：所有读取/统计/运行都在容器内执行
- Anti-Hallucination Strategy：统计必须来自解析脚本或测试输出；缺失必须写 UNKNOWN 并说明原因

---

## 9.总结与思考

### 实现亮点

- 源码级规则抽取与证据可追溯，实现了Rule → Scenario → Test 映射与可量化覆盖，实现了逻辑闭环。
- Docker Agent 执行模型保证复现。
- subprocess 黑盒驱动：贴近真实使用，不依赖 C++ ABI 绑定，避免了动态库版本麻烦。
- 实现CLI helper：补齐官方示例缺失的 Update/Delete/Replace/AddOrUpdate 入口
- Python 行覆盖率 96%，用coverage.py 实测

### 当前不足

- 4 个测试仍为 skip：BR-AoU-02（并发）、BR-Partition-02（跨分区路由）、BR-Query-05（query parser）、CFG-03（异步写队列）均属 UNKNOWN，没有找到明确实现。
- CFG/CG 规在测试里没有显式地用 ID 去关联，规则覆盖统计比较保守
- test_update_merges_old_field 的 MergeOldField 验证不够彻底：helper 每次传三个字段，没有真正测到“只更新某一个字段、其他字段保留原值”的场景

### 高 ROI 后续方向

- 扩展 CLI helper：支持部分字段更新，验证 MergeOldField 语义（BR-Upd-02）
- 动态 tracing + 静态分析：把那些现在还停留在“推测”状态的规则补成证据，提升规则的可信度
- 自动生成 fuzz/property-based tests，自动生成随机 query 和字段组合，覆盖 tokenizer 与 Query 组合边界
- 做Rule Diff 机制，代码版本变更后，只重新分析变动的那部分规则和测试，做到增量重建。

