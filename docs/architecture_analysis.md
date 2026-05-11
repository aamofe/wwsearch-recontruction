---
name: wwsearch架构调用链分析
overview: 对 /home/ubuntu/wwsearch-recontruction/wwsearch 做全局静态分析，基于源码证据输出模块结构、写入/查询调用链、存储/索引/tokenizer 架构；所有无法证实点标记 UNKNOWN，并产出仅“事实级”的 docs/architecture_analysis.md 草稿。
todos:
  - id: scan-build-targets
    content: 从 `wwsearch/CMakeLists.txt`/`wwsearch/build.sh` 提取目标、库关系、依赖集成方式，并在文档中给出可引用片段。
    status: pending
  - id: extract-public-api
    content: 从 `wwsearch/include/index_writer.h`、`wwsearch/include/searcher.h`、example/unittest 提取 API 签名、参数/返回值/错误类型与调用入口。
    status: pending
  - id: write-path-chain
    content: 以 `IndexWriter::InnerWriteDocuments` → `DocumentWriter::UpdateDocuments` → `VirtualDB::FlushBuffer` 为主线，补齐 WriteBuffer/Codec/ColumnFamily 的证据链，形成 Add→Storage→Index→Persist 调用链图。
    status: pending
  - id: query-path-chain
    content: 以 `Searcher::DoQuery` → `Query::CreateWeight` → `Scorer::Iterator` → `TopNCollector` 为主线，证据化 filter/sort/pagination，并标注 UNKNOWN（parse/planner/router）。
    status: pending
  - id: storage-index-tokenizer-concurrency
    content: 梳理 VirtualDB/RocksDB ColumnFamily schema、key 编码、merge operator、tokenizer 类型与并发控制点（锁/队列），并列出风险区域与 UNKNOWN。
    status: pending
  - id: draft-architecture-md
    content: 生成 `docs/architecture_analysis.md` 草稿（仅事实+UNKNOWN），包含 mermaid 模块图/调用链图与关键代码引用。
    status: pending
isProject: false
---

## 约束与产出
- **仅事实级源码认知**：所有结论必须能在源码中直接定位到文件与片段；看不到实现/无法确认的一律写 **UNKNOWN** 并附待验证位置。
- **禁止输出业务规则/BR-* 编号/覆盖率/推测**：文档只描述代码结构、调用关系、数据结构与接口形态。
- **输出物**：生成 `docs/architecture_analysis.md`（草稿，可迭代），包含模块结构图、调用链、类关系、关键入口、UNKNOWN、风险区域。

## 静态扫描范围（递归）
- 代码主干：`wwsearch/src/`、`wwsearch/include/`、`wwsearch/example/`、`wwsearch/unittest/`、`wwsearch/benchmark/`
- 依赖：`wwsearch/deps/`（重点：`deps/rocksdb/`、`deps/tokenizer/`、`deps/protobuf/`、`deps/snappy/`）
- 工具脚本：`wwsearch/build.sh`、`scripts/env.sh`

## 1) 项目结构识别（目录树/目标/依赖/namespace）
- **目录树（核心模块）**：基于 CMake 与 include/src 文件集合构建“核心模块树”，明确哪些目录参与 `wwsearch` 库编译。
  - 证据入口：`wwsearch/CMakeLists.txt` 中 `file(GLOB WWSEARCH_SRC_DIR ./src/*.cpp ./include/*.cc)` 与 `ADD_LIBRARY(wwsearch ...)`。
- **编译目标与库关系**：从 `wwsearch/CMakeLists.txt` 提取：
  - `wwsearch`（库）：链接 `rocksdb`、`tokenizer`、`libprotobuf.a`、`libsnappy.a`、`z pthread rt`。
  - `wwsearch_example`（可执行）：链接 `wwsearch`。
  - `wwsearch_ben`（可执行）：链接 `wwsearch`。
  - `wwsearch_ut`（可执行，`WITH_TESTS` 开关控制）：链接 `wwsearch gtest z pthread`。
- **third_party 依赖关系**：从 `add_subdirectory(${WWSEARCH_DIR}/deps/rocksdb)`、`add_subdirectory(${WWSEARCH_DIR}/deps/tokenizer)` 以及 `FIND_LIBRARY(PROTOBUF_LIB...)`、`FIND_LIBRARY(SNAPPY_LIB...)` 归纳依赖集成方式。
- **namespace 组织方式**：统计 `namespace wwsearch` 的实际分布与子命名空间（例如 `wwsearch::merge` 出现在 `include/virtual_db_rocks.h` / `src/virtual_db_rocks.cpp`）。

## 2) 公共 API 提取（include + example + unittest）
- **头文件 API 面**：以 `wwsearch/include/index_writer.h` 与 `wwsearch/include/searcher.h` 为主，提取并逐条列出：
  - `IndexWriter::{AddDocuments,UpdateDocuments,AddOrUpdateDocuments,ReplaceDocuments,DeleteDocuments,AddDocumentsWithoutRead}` 的真实签名（含默认参数）。
  - `Searcher::DoQuery` 的真实签名（含 offset/limit、filter/sorter、score_strategy_list、min_match_filter_num 等）。
- **错误/异常风格**：
  - 写入 API 返回 `bool`，单文档状态通过 `DocumentUpdater::Status()`（类型为 `SearchStatus`）回填（具体码与语义仅在出现的源码位置引用，不扩展推断）。
  - 查询 API 返回 `SearchStatus`。
- **调用入口**：
  - 示例入口：`wwsearch/example/example.cpp`（通过 `DefaultIndexWrapper` 打开 DB、调用 `indexer.index_writer_->AddDocuments`、调用 `Searcher::DoQuery` 并 `GetStoredFields`）。
  - UT 入口：`wwsearch/unittest/*_unit.cpp`（覆盖 add/update/delete/replace/查询/排序/过滤等路径的调用方式）。

## 3) 写入链路（Add → Storage → Index → Persist）证据化调用链
- **入口函数**：`IndexWriter::AddDocuments/UpdateDocuments/AddOrUpdateDocuments/ReplaceDocuments/DeleteDocuments`（见 `wwsearch/include/index_writer.h` 与 `wwsearch/src/index_writer.cpp`）。
- **中间层与事务边界（事实级）**：
  - `IndexWriter::InnerWriteDocuments` 中对 `VirtualDB::MultiGet` 的读取（`kStoredFieldColumn` 与条件性读取 `kDocValueColumn`），随后调用 `DocumentWriter::UpdateDocuments`。
  - `DocumentWriter::UpdateDocuments` 创建 `WriteBuffer`（`VirtualDB::NewWriteBuffer`），依次调用：
    - `RunTokenizer`（调用 `config_->GetTokenizer()->Do(document)`）
    - `MergeOldField`
    - `WriteStoredField`
    - `WriteInvertedIndex`
    - `WriteDocValue`
    - `WriteTableMeta`（当前实现片段显示为“Not support/return status”，需按源码原样记录）
    - `WriteDictionaryMeta`（当前实现返回空 `SearchStatus`）
  - **持久化点**：若 `store_buffer == nullptr`，调用 `VirtualDB::FlushBuffer(write_buffer)`；RocksDB 实现中落到 `rocksdb::DB::Write(rocksdb::WriteOptions(), write_batch)`（见 `wwsearch/src/virtual_db_rocks.cpp`）。
- **索引更新点**：以 `DocumentWriter::WriteInvertedIndex` / `WriteStoredField` / `WriteDocValue` 的实际写入列族（`StorageColumnType`）为准，补齐每类 key 的编码函数（`CodecImpl::{EncodeStoredFieldKey,EncodeInvertedKey,...}`）。
- **WAL/LSM 写入点**：仅记录可见事实：`VirtualDBRocksImpl::FlushBuffer` 调用 `db_->Write(...)`；以及 `VDBParams` / `InitDBOptions()` 中显式 WAL/compaction/memtable 参数（例如 `max_total_wal_size`、`rocks_num_levels`、`level0_*_trigger` 等）。
- **异常路径**：
  - MultiGet 失败、反序列化失败（`DeSerializeFromByte`）、tokenizer 失败、write batch 超限（`GetMaxWriteBatchSize()`）、FlushBuffer 失败等路径都在文档中以“触发点 + 状态码设置位置”列出。

## 4) 查询链路（DoQuery）证据化调用链
- **入口**：`Searcher::DoQuery`（`wwsearch/include/searcher.h` + `wwsearch/src/searcher.cpp`）。
- **执行链**：
  - 创建 `VirtualDBSnapshot` 与 `SearchContext(table,vdb,snapshot,config)`。
  - `weight = query.CreateWeight(&context, false, 0)`；`scorer = weight->GetScorer(&context)`。
  - 构造 `TopNCollector(table, offset, limit, this, &context, filter, sorter, score_strategy_list, ...)`。
  - 迭代 `scorer->Iterator()` 获取 docID，调用 `collector.Collect(docID, fieldId)`；最后 `collector.Finish()` 与 `collector.GetAndClearMatchDocs(docs)`。
- **Filter 顺序**：在 `TopNCollector::MatchFilter` 中按 `for (auto rule : *filter_)` 顺序逐个执行 `rule->Match(find_field)`，不短路；以 `min_match_filter_num_` 判定是否通过（见 `wwsearch/src/collector_top.cpp`）。
- **Sort 机制**：`TopNCollector` 使用 `std::priority_queue<Document*,...,Sorter>`；`Sorter` 对 `std::vector<SortCondition*>` 逐条件比较（见 `wwsearch/include/sorter.h`）。
- **Pagination**：
  - 收集阶段使用 `top_n_ = offset + limit` 控制 heap 容量。
  - 输出阶段 `GetAndClearMatchDocs` 使用 `push_front` 反向输出，并在最后用 `offset_` 删除前置元素（见 `wwsearch/src/collector_top.cpp`）。
- **Query Parse / Planner / Merge / 跨表路由**：当前可见代码中 Query 为显式构造（`BooleanQuery/AndQuery/OrQuery/PrefixQuery/...`），未发现独立的 parse/planner/router 组件；若后续在其他文件发现则补充，否则标记 **UNKNOWN** 并给出全仓定位结果。

## 5) 核心组件职责（存储/索引/tokenizer/并发模型）
- **存储层**：
  - 抽象：`VirtualDB`（`wwsearch/include/virtual_db.h`）提供 snapshot、MultiGet、Iterator、FlushBuffer 等。
  - RocksDB 实现：`VirtualDBRocksImpl`（`wwsearch/include/virtual_db_rocks.h` / `wwsearch/src/virtual_db_rocks.cpp`）使用 ColumnFamily（`StorageColumnType` 枚举）与 `WriteBatch`。
  - 列族 schema：`StorageColumnType`（`wwsearch/include/storage_type.h`）明确 stored/inverted/docvalue/meta/dictionary 等列。
  - key prefix 策略：通过 `CodecImpl` 的编码函数与注释中的 key layout（`wwsearch/include/codec_impl.h`）+ 实现文件（`wwsearch/src/codec_impl.cpp`，后续读取）固化。
- **索引层**：
  - 正排：`kStoredFieldColumn`（存储 document 的 pb/序列化字节）。
  - 倒排：`kInvertedIndexColumn`（term -> doclist），并由 RocksDB merge operator `DocListMergeOperator` 合并（`wwsearch/include/virtual_db_rocks.h` / `wwsearch/src/virtual_db_rocks.cpp`）。
  - doc value：`kDocValueColumn`。
  - partition/table：`TableID {business_type, partition_set}` 作为 key 的前缀部分（见 `wwsearch/include/storage_type.h` 与 codec 注释）。
- **tokenizer**：
  - 接口：`Tokenizer`（`wwsearch/include/tokenizer.h`）提供 `Do(document)` 与 `BuildTerms`。
  - 实现：`TokenizerMMSEG`（`wwsearch/include/tokenizer_mmseg.h` / `wwsearch/src/tokenizer_mmseg.cpp`）与 `TokenizerSpaceImpl`（`wwsearch/include/tokenizer_impl.h` / `wwsearch/src/tokenizer_impl.cpp`）。
  - 使用点：写入路径 `DocumentWriter::RunTokenizer`（`wwsearch/src/document_writer.cpp`）明确调用 `config_->GetTokenizer()->Do(document)`。
  - 查询路径的 tokenizer 使用：目前未在 Query/Weight 创建过程中看到 `BuildTerms` 的调用；若后续未发现，将在文档中标记 **UNKNOWN（query-term normalize/tokenize）**。
- **并发模型**：
  - merge operator 内部锁/heap：`merge::OptimizeMerger`（`wwsearch/src/virtual_db_rocks.cpp`）包含 `std::mutex locks_[]`。
  - tokenizer 并发：`TokenizerMMSEG` 使用 `ThreadHashLock` + 多 `SegmenterManager`（`wwsearch/include/tokenizer_mmseg.h` / `wwsearch/src/tokenizer_mmseg.cpp`）。
  - RocksDB 写入异步队列：存在 `VirtualDBRocksWriteQueue`/`DbRocksWriteQueue` 类型字段（`write_queue_`），但是否启用取决于构造参数；默认 `DefaultIndexWrapper` 传 `nullptr`（`wwsearch/src/index_wrapper.cpp`）。如其实现与启用方式需进一步阅读相关文件并据实补充。

## 文档生成（草稿）结构
- `docs/architecture_analysis.md` 章节：
  - 项目结构与构建目标（含依赖树）
  - 模块结构图（Mermaid：模块/库依赖、核心类关系）
  - 公共 API 清单（IndexWriter/Searcher 等）
  - 写入链路（文本流程图 + 调用链 + 关键源码位置）
  - 查询链路（文本流程图 + filter/sort/pagination 证据）
  - 存储架构（VirtualDB/ColumnFamily/WriteBatch/merge operator）
  - 索引架构（stored/inverted/docvalue + key 编码）
  - tokenizer 架构（实现/并发/使用点）
  - UNKNOWN 汇总（按主题列出待确认文件/函数）
  - 风险区域（仅基于代码可见的风险点：例如线程安全、资源释放、参数边界、硬编码上限；不做业务推断）

## 待补齐的源码阅读点（为保证“事实级”）
- `wwsearch/src/codec_impl.cpp`：确认 key 编码的字节布局（prefix/field_id/term）与 Debug* 输出格式。
- `wwsearch/src/document_writer.cpp` 中 `WriteStoredField/WriteInvertedIndex/WriteDocValue` 的具体列族操作（Put/Merge/DeleteRange）与异常路径。
- `wwsearch/*weight*/*scorer*/*iterator*`：确认 inverted index 读取点、prefix query 扫描方式（是否 iterator seek/next），以及 query “planner”是否仅是 `Query::CreateWeight` 组合。
- `wwsearch/src/virtual_db_mock.cpp`：确认 mock 存储实现与持久化（若存在）。
- `wwsearch/include/virtual_db_rocks_write_queue.h` + `wwsearch/src/virtual_db_rocks_write_queue.cpp`：确认 async queue/线程模型与事务边界。
