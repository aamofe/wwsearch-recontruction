# wwsearch 集成测试剧本（Integration Test Scenarios）

> 目标：基于 `docs/business_rules_wwsearch.md` 中规则（BR-*）与仓库中可执行程序/示例（`wwsearch_example`）形成**可落地的集成测试剧本**。
>
> 约束说明：
> - 当前仓库中官方示例 `wwsearch/example/example.cpp` 仅覆盖 **Add + Query + GetStoredFields**（含 Filter/Sort）。
> - Update/Delete/Replace 的真实调用方式在 `wwsearch/unittest/*.cpp` 中通过 C++ API 覆盖，但**未提供对应 CLI**；若仅允许“subprocess 调用官方 example”，则这些场景需要额外 helper 可执行程序或启用 `WITH_TESTS` 构建 `wwsearch_ut` 进行间接验证。
> - 对 `UNKNOWN` / `PARTIAL` 规则：按要求在 Expected Result 中标记 **Expected Failure**。

---

## TS-ww-Add-01

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Add-01 |
| 关联规则ID | BR-Add-01 |
| 测试目标 | 新文档 Add 成功并可被 Query 命中 |
| Preconditions | 已编译可执行 `wwsearch_example`；准备独立 RocksDB 数据目录 |
| Steps | 1) 使用空数据目录运行 `wwsearch_example <db_dir>`  2) 观察 Add 状态输出 3) 观察 Query 输出 |
| Expected Result | Add 返回 Success（3 个 doc）且至少一个 query `match > 0` |
| Validation Method | 解析 `stdout`：包含 `After Add Status:` 且出现 3 次 `Code:Success`；包含至少一条 `query: match` 且数值大于 0 |

---

## TS-ww-Add-02

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Add-02 |
| 关联规则ID | BR-Add-01 |
| 测试目标 | 重复 Add 同一批 docid 时失败（duplicate） |
| Preconditions | 同一个 RocksDB 数据目录可复用；`wwsearch_example` 每次固定写入 docid=1..3 |
| Steps | 1) 第一次运行 `wwsearch_example <db_dir>` 2) 第二次用同一个 `<db_dir>` 再运行一次 |
| Expected Result | 第二次 Add 失败并打印 `Add Document return error` 或对应失败状态 |
| Validation Method | 解析第二次 `stdout`：包含 `Add Document return error`（或 `Code:Failure` 至少 1 次） |

---

## TS-ww-Upd-01

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Upd-01 |
| 关联规则ID | BR-Upd-01、BR-Upd-02 |
| 测试目标 | Update 存在文档成功；缺失字段按 MergeOldField 保留 |
| Preconditions | 需要可触达 `IndexWriter::UpdateDocuments` 的真实入口（官方 example 不包含） |
| Steps | 1) Add 文档（含字段A/B）2) Update 同 docid 仅更新字段A 3) GetStoredFields 验证字段B 仍存在 |
| Expected Result | Update 成功，字段A更新，字段B保留 |
| Validation Method | **SKIP（阻塞原因：官方 `wwsearch_example` 未提供 Update CLI；需新增 helper 可执行程序或启用构建 `wwsearch_ut` 并新增可脚本化入口）** |

---

## TS-ww-AoU-01

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-AoU-01 |
| 关联规则ID | BR-AoU-01 |
| 测试目标 | AddOrUpdate：不存在时插入、存在时更新 |
| Preconditions | 需要可触达 `IndexWriter::AddOrUpdateDocuments` 的真实入口（官方 example 不包含） |
| Steps | 1) AoU 写入不存在 doc 2) AoU 再次写入同 docid（不同字段值）3) Query/Fetch 验证更新生效 |
| Expected Result | 两次 AoU 均成功，第二次结果覆盖/更新 |
| Validation Method | **SKIP（阻塞原因同上：缺少官方可执行入口）** |

---

## TS-ww-Replace-01

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Replace-01 |
| 关联规则ID | BR-Replace-01 |
| 测试目标 | Replace 跳过 MergeOldField（缺字段不会补齐） |
| Preconditions | 需要可触达 `IndexWriter::ReplaceDocuments` 的真实入口（官方 example 不包含） |
| Steps | 1) Add 文档（字段A、字段B）2) Replace 同 docid（只带字段A）3) Fetch 验证字段B 消失 |
| Expected Result | 字段B 不再存在；**Expected Failure**：Replace 语义在规则中为 PARTIAL，仅能确认“跳过 MergeOldField” |
| Validation Method | **Expected Failure + SKIP（缺少官方可执行入口；且规则 PARTIAL 需额外证据）** |

---

## TS-ww-Del-01

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Del-01 |
| 关联规则ID | BR-Del-01 |
| 测试目标 | Delete 后查询不可命中（删除后查询） |
| Preconditions | 需要可触达 `IndexWriter::DeleteDocuments` 的真实入口（官方 example 不包含） |
| Steps | 1) Add 文档 2) Delete 文档 3) Query 同 term |
| Expected Result | Delete 后 query 不再返回该 docid |
| Validation Method | **SKIP（阻塞原因同上：缺少官方可执行入口）** |

---

## TS-ww-Query-01

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Query-01 |
| 关联规则ID | BR-Query-01、BR-Query-02、BR-Query-03、BR-Query-04 |
| 测试目标 | Query + Filter + Sort + Pagination 基本链路可用 |
| Preconditions | `wwsearch_example` 内置 AndQuery(两 term)、RangeFilter、NumericSortCondition、offset=0 limit=10 |
| Steps | 1) 运行 `wwsearch_example <db_dir>` 2) 观察每次 query 的 filter/sort 打印与 match 数 |
| Expected Result | `DoQuery` 返回 OK，能输出 `query: match <n>`；n 在合理范围（0..3） |
| Validation Method | 解析 `stdout`：出现 `filter=`、`term=`、`query: match` 关键字；并确保程序退出码为 0 |

---

## TS-ww-Query-02（多字段查询 / 非法参数）

| 字段 | 内容 |
| --- | --- |
| 场景ID | TS-ww-Query-02 |
| 关联规则ID | BR-Query-05 |
| 测试目标 | 多字段查询/Query parser/路由能力验证 |
| Preconditions | 规则状态为 UNKNOWN；官方示例使用 field_id=0 的 BooleanQuery，不存在 query-string parser |
| Steps | 1) 构造多字段 query（field_id=0 与 field_id=1）2) 执行查询并验证命中差异 |
| Expected Result | **Expected Failure**：规则 UNKNOWN，当前仓库内缺少可证实的 parser/路由实现 |
| Validation Method | **Expected Failure + SKIP（缺少实现入口与证据；需补齐上层 parser/路由代码后再补测试）** |

