# wwsearch 业务规则文档（最终版）

## 1. 项目元数据

- **项目名称**: `wwsearch`
- **GitHub URL**: **UNKNOWN**（当前工作目录不是 git 仓库，无法从 `git remote` 复现 URL）
- **分析日期**: `2026-05-11`
- **commit hash**: **UNKNOWN**（`/home/ubuntu/wwsearch-recontruction` 非 git 仓库，无法 `git rev-parse HEAD`）
- **分析范围**:
  - `wwsearch/src/`
  - `wwsearch/include/`
  - `wwsearch/example/`
  - `wwsearch/unittest/`
  - `wwsearch/benchmark/`
  - `wwsearch/deps/`（仅用于确认依赖集成方式与接口边界）
  - `wwsearch/build.sh`、`scripts/env.sh`
- **分析方法**:
  - 全局静态阅读 + 关键符号反向追踪（API→实现→存储/编码→错误码）
  - 规则抽取原则：**无源码证据不成规则**；不确定项标记 **UNKNOWN** 并给出待验证位置

## 2. 架构概览

### 2.1 组件总览（结构化表格）

| 模块 | 核心类型/入口 | 主要职责（仅源码证据） | 关键源码位置 |
|---|---|---|---|
| 存储层 | `VirtualDB` / `VirtualDBRocksImpl` | Snapshot/MultiGet/Iterator/FlushBuffer（WriteBatch） | `wwsearch/include/virtual_db.h`, `wwsearch/include/virtual_db_rocks.h`, `wwsearch/src/virtual_db_rocks.cpp` |
| 索引层（正排） | `kStoredFieldColumn` | 存储 `StoreDocument` protobuf bytes | `wwsearch/include/storage_type.h`, `wwsearch/src/document_writer.cpp` |
| 索引层（倒排） | `kInvertedIndexColumn` + `DocListMergeOperator` | `term -> doclist`，写入用 `Merge`，RocksDB merge operator 合并 doclist | `wwsearch/src/document_writer.cpp`, `wwsearch/include/virtual_db_rocks.h`, `wwsearch/src/virtual_db_rocks.cpp` |
| DocValue | `kDocValueColumn` | 存储仅包含 `DocValue` flag 字段的 `StoreDocument` | `wwsearch/src/document_writer.cpp`, `wwsearch/src/document.cpp` |
| Query Engine | `Searcher::DoQuery` | Query→Weight→Scorer→Collector；filter/sort/pagination | `wwsearch/include/searcher.h`, `wwsearch/src/searcher.cpp`, `wwsearch/include/collector_top.h`, `wwsearch/src/collector_top.cpp` |
| Tokenizer | `Tokenizer` / `TokenizerMMSEG` | 写入时 `Tokenizer::Do(document)` 构建 `IndexField::Terms()` | `wwsearch/include/tokenizer.h`, `wwsearch/include/tokenizer_mmseg.h`, `wwsearch/src/document_writer.cpp` |
| Partition/Table | `TableID` + `CodecImpl` | `business_type + partition_set` 作为 key 前缀 | `wwsearch/include/storage_type.h`, `wwsearch/src/codec_impl.cpp` |

### 2.2 模块图（文本）

```
                    +----------------------+
                    |  DefaultIndexWrapper |
                    |  (wires components)  |
                    +----------+-----------+
                               |
                               v
  +-----------+     +------------------+      +----------------------+
  | Tokenizer |<----|   IndexConfig    |----->|      VirtualDB       |
  | (MMSEG)   |     | (Codec/VDB/Tok)  |      | (Rocks/Mock impl)    |
  +-----------+     +--------+---------+      +----------+-----------+
                            |                           |
                            v                           v
                     +-------------+             +--------------+
                     | IndexWriter |             | WriteBuffer  |
                     | (API entry) |             | (WriteBatch) |
                     +------+------+\            +------+-------+
                            |       \                   |
                            v        \                  v
                     +-------------+  \          +---------------+
                     | Document    |   \         | RocksDB DB     |
                     | Writer      |    \        | ColumnFamilies |
                     +------+------+     \       +---------------+
                            |
                            v
                +------------------------+
                | CodecImpl (key encode) |
                +------------------------+

  Query path:
  Searcher::DoQuery -> Query::CreateWeight -> Weight::GetScorer -> Collector(TopN)
```

### 2.3 写入链路（事实级调用链）

```
IndexWriter::{Add/Update/AddOrUpdate/Replace/Delete}Documents
  -> IndexWriter::InnerWriteDocuments
      -> VirtualDB::MultiGet(kStoredFieldColumn[, kDocValueColumn])
      -> DocumentWriter::UpdateDocuments
          -> RunTokenizer
          -> MergeOldField (skip for Delete/Replace)
          -> WriteStoredField (Put/Delete)
          -> WriteInvertedIndex (Merge with OK/Delete doc state)
          -> WriteDocValue (Put/Delete)
          -> (WriteTableMeta / WriteDictionaryMeta are "Not support"/empty in current code)
          -> VirtualDB::FlushBuffer(WriteBuffer)
              -> VirtualDBRocksImpl::FlushBuffer
                  -> rocksdb::DB::Write(WriteOptions(), WriteBatch)
```

### 2.4 查询链路（事实级调用链）

```
Searcher::DoQuery
  -> VirtualDB::NewSnapshot
  -> Query::CreateWeight
  -> Weight::GetScorer
  -> iterate Scorer::Iterator() docid stream
  -> TopNCollector::Collect (buffer)
      -> InnerPurge:
          -> Searcher::GetDocValue (MultiGet kDocValueColumn/kStoredFieldKey)
          -> MatchFilter (vector order; no short-circuit; min_match threshold)
          -> optional GetStoredFields + ScoreStrategy
          -> priority_queue Sorter (SortCondition chain)
          -> pagination via top_n=offset+limit and final offset drop
  -> VirtualDB::ReleaseSnapshot
```

## 3. API 规格表

> 约束：仅列出能从头文件与实现直接确认的信息。错误码详见 `wwsearch/include/search_status.h`。

| API | 参数 | 返回值 | 前置条件 | 后置条件 | 错误路径 | 源码位置 |
|---|---|---|---|---|---|---|
| `IndexWriter::AddDocuments` | `(const TableID&, std::vector<DocumentUpdater*>&, std::string* store_buffer=nullptr, SearchTracer* tracer=nullptr)` | `bool` | `DocumentID != 0`；目标文档在 `kStoredFieldColumn` **不存在** | 成功则写入 stored/inverted/docvalue，并 `FlushBuffer` 或输出 `store_buffer` | 文档已存在：`kDocumentExistStatus`；序列化/tokenizer/rocksdb 等错误透传到 `DocumentUpdater::Status()`；批次失败传播 `kOtherDocumentErrorStatus` | `wwsearch/include/index_writer.h`, `wwsearch/src/index_writer.cpp`, `wwsearch/src/document_writer.cpp` |
| `IndexWriter::UpdateDocuments` | 同上 | `bool` | `DocumentID != 0`；目标文档在 `kStoredFieldColumn` **存在且可反序列化** | 成功则更新 stored/inverted/docvalue（含 MergeOldField） | old 解码失败：`kSerializeErrorStatus`；MultiGet/FlushBuffer 错误 | 同上 |
| `IndexWriter::AddOrUpdateDocuments` | 同上 | `bool` | `DocumentID != 0` | 不存在则视为可新增；存在则解码 old 并进入更新路径 | 并发一致性/原子性：**UNKNOWN**（无显式锁/事务证据） | 同上 |
| `IndexWriter::ReplaceDocuments` | 同上 | `bool` | `DocumentID != 0` | Replace 路径 **跳过 MergeOldField**；仍会写 stored/inverted/docvalue | old 解码失败（当 old 存在且解码失败）；WriteBatch/Flush 失败 | `wwsearch/src/document_writer.cpp`（MergeOldField skip）、`wwsearch/src/index_writer.cpp` |
| `IndexWriter::DeleteDocuments` | 同上 | `bool` | `DocumentID != 0`；old 文档需可解码以获得 old terms（用于倒排 tombstone） | stored-field Delete；docvalue 条件 Delete；倒排 Merge 写入 delete-state | old 解码失败：`kSerializeErrorStatus`；WriteBuffer/Flush 失败 | `wwsearch/src/document_writer.cpp`, `wwsearch/src/index_writer.cpp` |
| `Searcher::DoQuery` | `(const TableID&, Query&, size_t offset, size_t limit, std::vector<Filter*>* filter, std::vector<SortCondition*>* sorter, std::list<DocumentID>& docs, ... )` | `SearchStatus` | 调用方显式构造 Query；`IndexConfig` 已绑定 VDB/Codec | 输出 docid 列表（按 filter/sort/pagination） | scorer==nullptr：`kScorerErrorStatus`；collector/context status 透出 | `wwsearch/include/searcher.h`, `wwsearch/src/searcher.cpp`, `wwsearch/src/collector_top.cpp` |

## 4. 业务规则明细

> 本节规则内容来源：`docs/rules_analysis.md`（规则抽取时已附源码证据）。此处做“最终版编排”，并保持可追溯字段：Evidence/Status。

### 4.1 BR-Idx

- **BR-Idx-01**: TableID 编码为 key 前缀（`business_type + partition_set`）  
  - **Preconditions**: 需要构造 stored/inverted/meta key  
  - **Postconditions**: key 前缀固定  
  - **Error Handling**: 无（调用方负责）  
  - **Evidence**: `wwsearch/src/codec_impl.cpp:28-34`, `:79-86`  
  - **Status**: IMPLEMENTED

- **BR-Idx-02**: DocumentID 不能为 0  
  - **Preconditions**: `IndexWriter::InnerWriteDocuments`  
  - **Postconditions**: per-doc `kDocumentIDCanNotZero` + batch fail  
  - **Error Handling**: `SearchStatus` 回填  
  - **Evidence**: `wwsearch/src/index_writer.cpp:239-247`  
  - **Status**: IMPLEMENTED

- **BR-Idx-03**: StorageColumnType 列族顺序固定（不允许变更顺序）  
  - **Evidence**: `wwsearch/include/storage_type.h:53-71`  
  - **Status**: IMPLEMENTED

- **BR-Idx-04**: 倒排 key 直接拼接 term bytes（Decode 剩余全为 term）  
  - **Evidence**: `wwsearch/src/codec_impl.cpp:79-100`  
  - **Status**: IMPLEMENTED

### 4.2 BR-Add

- **BR-Add-01**: AddDocuments 仅允许“文档不存在”写入  
  - **Evidence**: `wwsearch/src/index_writer.cpp:108-118`  
  - **Status**: IMPLEMENTED

### 4.3 BR-Upd

- **BR-Upd-01**: UpdateDocuments 必须解码 old stored/docvalue（条件性）  
  - **Evidence**: `wwsearch/src/index_writer.cpp:119-142`  
  - **Status**: IMPLEMENTED

- **BR-Upd-02**: MergeOldField：新文档缺失字段保留旧字段（Delete/Replace 跳过）  
  - **Evidence**: `wwsearch/src/document_writer.cpp:805-824`  
  - **Status**: IMPLEMENTED

- **BR-Upd-03**: 倒排更新为“差分 Merge”（只对新增/删除 term 写入）  
  - **Evidence**: `wwsearch/src/document_writer.cpp:630-746`  
  - **Status**: IMPLEMENTED

### 4.4 BR-AoU

- **BR-AoU-01**: AddOrUpdate：不存在视为 OK；存在则解码 old 并继续  
  - **Evidence**: `wwsearch/src/index_writer.cpp:144-174`  
  - **Status**: IMPLEMENTED

- **BR-AoU-02**: AddOrUpdate 并发原子性/冲突解决  
  - **Evidence**: 仅能证实最终落盘为 `rocksdb::DB::Write(WriteOptions(), WriteBatch)`；未见锁/事务/compare-and-swap  
  - **Status**: UNKNOWN

### 4.5 BR-Replace

- **BR-Replace-01**: Replace 跳过 MergeOldField（“全量覆盖”的一部分证据）  
  - **Evidence**: `wwsearch/src/document_writer.cpp:810-813`  
  - **Status**: PARTIAL

### 4.6 BR-Del

- **BR-Del-01**: Delete：stored Delete + docvalue 条件 Delete + inverted tombstone Merge(delete-state)  
  - **Evidence**: `wwsearch/src/document_writer.cpp:472-516`, `:535-613`, `:615-750`  
  - **Status**: IMPLEMENTED

### 4.7 BR-Query

- **BR-Query-01**: DoQuery 主链（Weight→Scorer→Collector）  
  - **Evidence**: `wwsearch/src/searcher.cpp:24-90`  
  - **Status**: IMPLEMENTED

- **BR-Query-02**: Filter 顺序与 min_match_filter_num（vector order；不短路；match_count 阈值）  
  - **Evidence**: `wwsearch/include/collector_top.h:110-115`, `wwsearch/src/collector_top.cpp:309-333`  
  - **Status**: IMPLEMENTED

- **BR-Query-03**: Sort 机制（priority_queue + SortCondition 链）  
  - **Evidence**: `wwsearch/include/sorter.h:146-165`  
  - **Status**: IMPLEMENTED

- **BR-Query-04**: Pagination（top_n=offset+limit + 最终 offset drop）  
  - **Evidence**: `wwsearch/src/collector_top.cpp:109-123`  
  - **Status**: IMPLEMENTED

- **BR-Query-05**: Query parse/tokenizer/multi-field/partition routing  
  - **Evidence**: DoQuery 接收 `Query&` + 单 `TableID`；未见 parser/routing 组件  
  - **Status**: UNKNOWN

### 4.8 BR-Field

- **BR-Field-01**: 字段 flag 位定义  
  - **Evidence**: `wwsearch/include/index_field.h:80-87`  
  - **Status**: IMPLEMENTED

- **BR-Field-02**: StoredField（flag=0）序列化：value 依赖 StoredField；terms 依赖 NotStoreInvertTerm  
  - **Evidence**: `wwsearch/src/document.cpp:72-92`, `wwsearch/src/index_field.cpp:141-191`  
  - **Status**: IMPLEMENTED

- **BR-Field-03**: DocValue（flag=1）仅序列化 DocValue 字段  
  - **Evidence**: `wwsearch/src/document.cpp:61-88`  
  - **Status**: IMPLEMENTED

- **BR-Field-04**: SuffixBuild 默认 suffix_len=5（缺失时）  
  - **Evidence**: `wwsearch/src/index_field.cpp:228-235`  
  - **Status**: IMPLEMENTED

- **BR-Field-05**: DocValue 无字段时删除旧 docvalue（条件性）  
  - **Evidence**: `wwsearch/src/document_writer.cpp:558-584`  
  - **Status**: IMPLEMENTED

### 4.9 BR-Partition

- **BR-Partition-01**: TableID 结构定义  
  - **Evidence**: `wwsearch/include/storage_type.h:40-49`  
  - **Status**: IMPLEMENTED

- **BR-Partition-02**: partition routing strategy（跨分区/跨表路由）  
  - **Evidence**: 未在 `Searcher::DoQuery`/`IndexWriter` 内发现 fanout/merge  
  - **Status**: UNKNOWN

### 4.10 规则补充分组（来自源码但不在原始分组列表内）

- **BR-Write-03**: 批次失败传播（其余 OK 文档置 `kOtherDocumentErrorStatus`）  
  - **Evidence**: `wwsearch/src/index_writer.cpp:309-318`  
  - **Status**: IMPLEMENTED

- **BR-Write-04**: 持久化边界（FlushBuffer 或返回 store_buffer WriteBatch bytes）  
  - **Evidence**: `wwsearch/src/document_writer.cpp:89-112`, `wwsearch/src/virtual_db_rocks.cpp:584-592`, `wwsearch/src/write_buffer_rocks.cpp:28-35`  
  - **Status**: IMPLEMENTED

## 5. 配置规则（CFG-*）

- **CFG-01**: RocksDB 参数由 `VDBParams` 提供默认值并写入 `rocksdb::Options`  
  - **Status**: IMPLEMENTED
  - **Evidence**: `wwsearch/include/virtual_db.h:32-85`, `wwsearch/src/virtual_db_rocks.cpp:671-699`

- **CFG-02**: 单次写入使用默认 `rocksdb::WriteOptions()`（未显式配置 disableWAL/sync）  
  - **Status**: IMPLEMENTED
  - **Evidence**: `wwsearch/src/virtual_db_rocks.cpp:584-592`

- **CFG-03**: 异步写队列 `DbRocksWriteQueue` 的实现/语义  
  - **Status**: UNKNOWN
  - **Evidence**: 接口存在 + FlushBuffer 分支存在，但默认 wrapper 传 `nullptr`，且队列实现无法在当前仓库证实完整语义  

## 6. 代码生成规则（CG-*）

- **CG-01**: `search_store.proto` → `search_store.pb.h`（protoc 生成）  
  - **Status**: IMPLEMENTED
  - **Evidence**: `wwsearch/include/search_store.pb.h:1-3`

- **CG-02**: Document 使用 protobuf Serialize/Parse（stored/docvalue value）  
  - **Status**: IMPLEMENTED
  - **Evidence**: `wwsearch/src/document.cpp:72-109`

## 7. 覆盖度矩阵（基于 docs/rules_analysis.md 的实际规则条目）

> 记号映射：✅=IMPLEMENTED，⚠️=PARTIAL，❌=UNKNOWN  
> 覆盖率：\((✅ + 0.5×⚠️) / Total × 100%\)

| 模块/规则类别 | 总规则数 | ✅ | ⚠️ | ❌ | 覆盖率 |
|---|---:|---:|---:|---:|---:|
| BR-Idx | 4 | 4 | 0 | 0 | 100.00% |
| BR-Add | 1 | 1 | 0 | 0 | 100.00% |
| BR-Upd | 3 | 3 | 0 | 0 | 100.00% |
| BR-AoU | 2 | 1 | 0 | 1 | 50.00% |
| BR-Replace | 1 | 0 | 1 | 0 | 50.00% |
| BR-Del | 1 | 1 | 0 | 0 | 100.00% |
| BR-Query | 5 | 4 | 0 | 1 | 80.00% |
| BR-Field | 5 | 5 | 0 | 0 | 100.00% |
| BR-Partition | 2 | 1 | 0 | 1 | 50.00% |
| BR-Write | 2 | 2 | 0 | 0 | 100.00% |
| CFG | 3 | 2 | 0 | 1 | 66.67% |
| CG | 2 | 2 | 0 | 0 | 100.00% |
| **Total** | **31** | **26** | **1** | **4** | **85.48%** |

## 8. 缺口优先级（P0/P1/P2）

### P0（阻断正确性/一致性验证）

- **P0-1 并发一致性/原子性缺口（BR-AoU-02）**：缺少可证实的锁/事务/冲突解决语义，需动态验证与补充实现证据。
- **P0-2 跨分区/跨表路由缺口（BR-Partition-02 / BR-Query-05）**：当前 DoQuery 仅单 `TableID`，若业务需要跨分区检索，必须在上层实现并提供证据链。

### P1（功能可用但行为不完整或实现缺失）

- **P1-1 Replace 完整语义缺口（BR-Replace-01=PARTIAL）**：可证实“跳过 MergeOldField”，但“旧倒排清理/覆盖语义”需要更完整证据或动态验证。
- **P1-2 异步写队列缺口（CFG-03）**：接口存在但语义/实现无法在 repo 内证实。

### P2（可用性/可维护性风险）

- **P2-1 store_buffer 协议风险**：必须为 RocksDB WriteBatch bytes（否则注释提示可能 corruption）。
- **P2-2 ColumnFamily 枚举顺序兼容风险**：注释要求不可变更顺序。

## 9. 测试建议（每条规则：正向/边界/异常）

> 说明：测试建议仅基于当前源码可见行为编排，不推测“应有业务语义”。若需并发/路由等 UNKNOWN 行为，测试以“验证缺口/复现差异”为目标。

### BR-Idx-01
- 正向：不同 `TableID` 写入相同 `DocumentID`，确认 key 前缀不同导致数据隔离（读取需按相同 `TableID` 才命中）。
- 边界：`business_type=0`、`partition_set=0` 的编码/调试输出（只验证编码字节长度与可解码）。
- 异常：构造错误长度的 inverted_key 调 `DecodeInvertedKey`，应返回 false（`size<10`）。

### BR-Idx-02
- 正向：`DocumentID=1` 写入成功。
- 边界：批次中混入 `DocumentID=0` 与正常文档，验证整体返回 false。
- 异常：检查 `DocumentID=0` 的 `DocumentUpdater::Status().GetCode()==kDocumentIDCanNotZero`。

### BR-Idx-03
- 正向：对 `kStoredFieldColumn/kInvertedIndexColumn/kDocValueColumn` 分别 Put/Merge 后可读回（RocksDB 模式）。
- 边界：枚举遍历到 `kMaxColumn-1` 做 ColumnFamily 初始化检查（若有 Open 测试）。
- 异常：变更枚举顺序会破坏数据读写（此项仅建议作为“禁止变更”单测/编译期断言策略）。

### BR-Idx-04
- 正向：`EncodeInvertedKey`+`DecodeInvertedKey` round-trip（含 term）。
- 边界：term 为空串的 key 编码/解码。
- 异常：term 包含 `\0` 字节时，`term=key.ToString()` 的行为验证（仅验证 byte-preserve）。

### BR-Add-01
- 正向：AddDocuments 插入新 doc 成功，并能 DoQuery 命中。
- 边界：同一批次 2 个不同 docid 均不存在 → 均成功。
- 异常：对已存在 docid 再 AddDocuments，应返回 false 且 du 状态为 `kDocumentExistStatus`（或透传存储状态）。

### BR-Upd-01
- 正向：先 Add，再 Update（修改部分字段）成功。
- 边界：Update 时 docvalue 不存在/存在两种路径（取决于旧字段 flag）。
- 异常：人为写入损坏的 stored-field bytes（或 mock 注入），Update 应触发 `kSerializeErrorStatus`。

### BR-Upd-02
- 正向：Update 新文档缺少某 field_id，确认写后 stored-field 仍包含旧字段。
- 边界：Replace 模式下同样缺字段，确认不会补齐（与 Update 对比）。
- 异常：old_document 为空（not-exist）时，MergeOldField 不应崩溃（需结合 AddOrUpdate not-exist 路径）。

### BR-Upd-03
- 正向：更新前后 terms 差分：新增 term 写入 OK；删除 term 写入 delete-state（可通过倒排读取/合并后查询验证）。
- 边界：new&old 都有同 term（flag=3）不写入 merge operand（可通过写 batch kvcount 变化间接验证）。
- 异常：WriteBuffer::Merge 返回错误时应中止并返回错误 status。

### BR-AoU-01
- 正向：不存在时 AddOrUpdate 等价于插入。
- 边界：存在时 AddOrUpdate 走解码 old 并合并字段（验证旧字段保留）。
- 异常：old 解码失败时批次失败并设置 `kSerializeErrorStatus`。

### BR-AoU-02（UNKNOWN）
- 正向：并发两写同一 doc（不同字段更新），记录最终结果（用于“证伪/证实”原子性假设）。
- 边界：并发一写 delete 一写 update 的竞争序列，观察倒排 tombstone 与 stored 覆盖结果。
- 异常：高并发压测下检查 `WriteBatch`/MergeOperator 相关崩溃或错误码。

### BR-Replace-01（PARTIAL）
- 正向：Replace 不补齐旧字段（缺字段时写后 stored-field 缺失该字段）。
- 边界：Replace old 不存在也允许继续（需验证 index_writer replace 分支的 not-exist 处理）。
- 异常：Replace 时 old 解码失败（当 old 存在）触发 `kSerializeErrorStatus`。

### BR-Del-01
- 正向：Delete 后 `GetStoredFields` 读不到（NotFound 或等价状态），且查询结果不再包含 docid（依赖 tombstone 合并语义，需通过实际查询验证）。
- 边界：旧文档无 docvalue 字段时 Delete 不应对 `kDocValueColumn` 做 Delete（验证 write batch 不包含该 delete）。
- 异常：old terms 缺失（NotStoreInvertTerm）场景下 Delete 行为差异记录（用于风险验证，不做推断）。

### BR-Query-01
- 正向：BooleanQuery/AndQuery/OrQuery/PrefixQuery 各自能走通 DoQuery。
- 边界：空结果（无匹配 term）返回 OK 且 docs 为空。
- 异常：scorer==nullptr 时返回 `kScorerErrorStatus`（需要构造触发条件，若无法构造则记录为 UNKNOWN）。

### BR-Query-02
- 正向：多个 filter 全匹配时通过。
- 边界：`min_match_filter_num=0` 情况下验证构造器会把其置为 `filter->size()`。
- 异常：filter 字段缺失时 `Match(nullptr)` 返回 false，导致过滤（验证 RangeFilter/EqualFilter 等实现）。

### BR-Query-03
- 正向：NumericSortCondition desc/asc 排序结果符合比较器实现。
- 边界：缺字段/类型不匹配时按 docid 兜底排序。
- 异常：多个 SortCondition 链式比较一致性（无死循环/崩溃）。

### BR-Query-04
- 正向：offset=0,limit=K 返回 K 条（若命中足够）。
- 边界：offset>0 返回跳过前 offset 的结果。
- 异常：offset 超过命中数量返回空而非错误。

### BR-Query-05（UNKNOWN）
- 正向：上层若有 query-string parser，应对照 DoQuery 的 `Query&` 接口补齐证据并新增测试；当前 repo 内无法给出实现测试。
- 边界：Tokenizer::BuildTerms 在 query 路径是否使用（当前静态链路未见，需补证据）。
- 异常：跨分区 routing 的 fanout/merge 若在上层实现，需加入一致性与去重测试。

### BR-Field-01..05 / BR-Partition-01..02 / BR-Write-03..04 / CFG-01..03 / CG-01..02

> 这些规则的测试建议请直接复用 `docs/rules_analysis.md` 对应规则的“调用链 + 错误路径”构造用例；其中 UNKNOWN 项（BR-Partition-02、CFG-03）必须以“验证缺口”为目标设计测试。

---

## 附：输入文档

- `docs/architecture_analysis.md`
- `docs/rules_analysis.md`

