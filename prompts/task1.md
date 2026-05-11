1.phase1

```
# 任务：wwsearch 架构与调用链分析（禁止输出业务规则）

你是一名资深 C++ 静态分析工程师与搜索引擎架构专家。

目标：
对 `/workspace/wwsearch/` 仓库进行全局静态分析，
建立：

* 模块结构图
* 核心组件关系
* 写入链路
* 查询链路
* 存储架构
* 索引架构
* tokenizer 架构

⚠️ 当前阶段禁止：

* 输出业务规则
* 输出 BR-* 编号
* 输出覆盖率
* 推测行为
* 生成最终文档

只允许：

* 建立事实级源码认知
* 提取调用关系
* 记录未确认点

---

# 分析范围

必须递归扫描整个仓库：

* src/
* include/
* example/
* unittest/
* deps/
* tools/
* scripts/

重点分析：

* CMakeLists.txt
* build.sh
* *.proto
* storage/
* index/
* query/
* tokenizer/
* analyzer/
* engine/
* codegen/

---

# 第一部分：项目结构识别

输出：

1. 仓库目录树（核心模块）
2. 编译目标
3. 静态库/动态库关系
4. third_party 依赖关系
5. namespace 组织方式

必须引用：

* 文件路径
* 关键代码片段

---

# 第二部分：公共 API 提取

分析：

* include/wwsearch/
* example/example.cpp
* unittest/

提取：

1. API 名称
2. 函数签名
3. 参数类型
4. 返回值
5. 异常/错误码
6. 调用入口

重点关注：

* AddDocuments
* UpdateDocuments
* AddOrUpdateDocuments
* ReplaceDocuments
* DeleteDocuments
* DoQuery

---

# 第三部分：写入链路分析

必须建立：

Add → Storage → Index → Persist

完整调用链。

要求：

1. 标记入口函数
2. 标记中间层
3. 标记事务边界
4. 标记索引更新点
5. 标记 WAL/LSM 写入点
6. 标记异常路径

输出：

* 调用链流程图（文本）
* 类关系
* 关键源码位置

---

# 第四部分：查询链路分析

分析：

DoQuery 的完整执行流程。

包括：

* Query Parse
* Tokenize
* Inverted Index Search
* Filter
* Sort
* Merge
* Pagination

要求：

1. 标记 query planner
2. 标记 filter 执行顺序
3. 标记排序机制
4. 标记 tokenizer 使用位置
5. 标记跨表路由逻辑

---

# 第五部分：核心组件职责分析

必须识别：

## 存储层

* RocksDB/LevelDB/LSM 关系
* KV schema
* key prefix 策略

## 索引层

* 正排索引
* 倒排索引
* doc value
* partition/table

## tokenizer

* 分词器类型
* analyzer pipeline
* token normalize

## 并发模型

* lock
* thread pool
* async queue

---

# 输出要求

生成：
docs/architecture_analysis.md

文档必须包含：

1. 模块结构图
2. 调用链
3. 类关系
4. 关键入口函数
5. 未确认点（UNKNOWN）
6. 风险区域

---

# 严格约束

禁止：

* 推测不存在的逻辑
* 根据函数名脑补行为
* 未看到实现就下结论
* 输出业务规则

如果无法确认：

* 标记 UNKNOWN
* 给出待验证源码位置

```

2.phase2

```
# 任务：wwsearch 业务规则重建（基于架构分析）

基于上一阶段生成的：

docs/architecture_analysis.md

继续对 `/workspace/wwsearch/` 进行源码分析。

目标：

重建：

* 业务规则体系（BR-*）
* 配置规则（CFG-*）
* 代码生成规则（CG-*）

⚠️ 本阶段禁止：

* 编造规则
* 推测行为
* 没有源码证据的规则

---

# 规则抽取要求

每条规则必须包含：

1. Rule ID
2. 规则名称
3. 规则描述
4. 前置条件
5. 后置条件
6. 边界条件
7. 错误处理
8. 调用链
9. 源码证据
10. 风险等级

---

# 必须抽取的规则类别

## BR-Idx-xx

索引与文档管理规则

包括：

* TableID 唯一性
* DocumentID 唯一性
* field_flag
* 分表策略
* key prefix

---

## BR-Add-xx

AddDocuments 行为

分析：

* id 不存在
* id 已存在
* rollback
* index update
* partial failure

---

## BR-Upd-xx

UpdateDocuments 行为

分析：

* merge/update 策略
* 未更新字段保留
* inverted index refresh
* field overwrite

---

## BR-AoU-xx

AddOrUpdateDocuments 行为

分析：

* 是否原子
* race condition
* lock 机制
* conflict resolution

---

## BR-Replace-xx

ReplaceDocuments 行为

分析：

* replace semantics
* full overwrite
* old index cleanup

---

## BR-Del-xx

DeleteDocuments 行为

分析：

* tombstone
* physical delete
* inverted index cleanup

---

## BR-Query-xx

DoQuery 行为

分析：

* query parse
* filter order
* sort order
* tokenizer
* ranking
* pagination
* multi-field query
* partition routing

---

## BR-Field-xx

字段规则

分析：

* kTokenizeFieldFlag
* kStoreFieldFlag
* kDocValueFieldFlag
* kInvertIndexFieldFlag

及其组合行为。

---

## BR-Partition-xx

分表规则

分析：

* TableID encoding
* business_type
* partition_set
* route strategy

---

# CFG-* 规则

分析：

* RocksDB 参数
* cache
* memory threshold
* WAL
* compaction
* thread pool

---

# CG-* 规则

分析：

* protobuf
* codegen
* generated schema
* serialization

---

# 输出要求

生成：

docs/rules_analysis.md

必须：

1. 每条规则有源码证据
2. 每条规则有调用链
3. 每条规则有异常路径
4. 每条规则标记：

   * IMPLEMENTED
   * PARTIAL
   * UNKNOWN

---

# 严格约束

禁止：

* 没证据的规则
* 用命名猜测行为
* 虚构原子性
* 虚构一致性保证
* 虚构事务机制

若规则无法确认：

输出：

STATUS: UNKNOWN

并说明：

* 缺失原因
* 需要动态验证的位置

```

3.phase3

```
# 任务：生成 wwsearch 业务规则文档（最终版）

基于：

* docs/architecture_analysis.md
* docs/rules_analysis.md

生成最终文档：

/workspace/wwsearch-reconstruction/docs/business_rules_wwsearch.md

---

# 文档结构

# 1. 项目元数据

包括：

* 项目名称
* GitHub URL
* 分析日期
* commit hash
* 分析范围
* 分析方法

---

# 2. 架构概览

包括：

* 存储层
* 索引层
* Query Engine
* Tokenizer
* Partition
* 写入链路
* 查询链路

要求：

* 使用结构化表格
* 使用模块图（文本）
* 不写空话

---

# 3. API 规格表

每个 API 必须包含：

| API | 参数 | 返回值 | 前置条件 | 后置条件 | 错误路径 | 源码位置 |

重点：

* AddDocuments
* UpdateDocuments
* ReplaceDocuments
* DeleteDocuments
* AddOrUpdateDocuments
* DoQuery

---

# 4. 业务规则明细

按：

* BR-Idx
* BR-Add
* BR-Upd
* BR-AoU
* BR-Replace
* BR-Del
* BR-Query
* BR-Field
* BR-Partition

分组。

每条规则必须包含：

1. Rule ID
2. 描述
3. Preconditions
4. Postconditions
5. Error Handling
6. Evidence
7. Status

---

# 5. 配置规则

CFG-*。

---

# 6. 代码生成规则

CG-*。

---

# 7. 覆盖度矩阵

格式：

| 模块/规则类别 | 总规则数 | ✅ | ⚠️ | ❌ | 覆盖率 |

覆盖率公式：

(✅ + 0.5×⚠️) / Total × 100%

要求：

* 基于实际源码
* 不允许推测

---

# 8. 缺口优先级

按：

* P0
* P1
* P2

分类。

---

# 9. 测试建议

每条规则至少包含：

* 正向测试
* 边界测试
* 异常测试

---

# 文档质量要求

必须：

* 可追溯
* 可验证
* 可测试
* 可复现

禁止：

* 空泛描述
* 无源码依据
* 推测性结论
* 虚构覆盖率
* 虚构一致性

若存在 UNKNOWN：

必须显式标记。

```

