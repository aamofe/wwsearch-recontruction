# wwsearch 规则体系重建（仅源码证据）

> 严格约束：本文件只记录**可由源码直接证实**的规则与行为；无法确认的点用 **STATUS: UNKNOWN** 并给出待验证位置。

## 0. 规则状态枚举

- **IMPLEMENTED**：在源码中存在明确实现路径，且能给出入口/调用链/异常路径证据。
- **PARTIAL**：存在部分实现或实现存在明显空洞/注释掉/仅部分条件覆盖。
- **UNKNOWN**：无法从当前仓库源码证实（缺失实现、缺少调用点、或行为需动态验证）。

## 1. BR-Idx-xx（索引与文档管理规则）

### BR-Idx-01 TableID 编码前缀规则

- **Rule ID**: BR-Idx-01
- **规则名称**: TableID 作为 key 前缀（business_type + partition_set）
- **规则描述**: `TableID{business_type, partition_set}` 被编码为所有主 key 的前缀，用于“表/分区”隔离。
- **前置条件**: 构造 key 时提供 `TableID`。
- **后置条件**: key 以 `AppendFixed8(business_type) + AppendFixed64(partition_set)` 开头。
- **边界条件**: **UNKNOWN**（business_type/partition_set 的取值范围与冲突策略未在此处定义）。
- **错误处理**: 无显式错误返回；依赖调用方提供正确的 `TableID`。
- **调用链**:
  - 写入：`IndexWriter::InnerWriteDocuments` / `DocumentWriter::`* → `CodecImpl::EncodeStoredFieldKey/EncodeInvertedKey`
  - 查询：`BooleanWeight::GetScorer` / `PrefixWeight::GetScorer` → `CodecImpl::EncodeInvertedKey`
- **源码证据**:

```28:34:/home/ubuntu/wwsearch-recontruction/wwsearch/src/codec_impl.cpp
AppendFixed8(document_key, table.business_type);
AppendFixed64(document_key, table.partition_set);
AppendFixed64(document_key, document_id);
```

```79:86:/home/ubuntu/wwsearch-recontruction/wwsearch/src/codec_impl.cpp
AppendFixed8(key, table.business_type);
AppendFixed64(key, table.partition_set);
AppendFixed8(key, field_id);
AppendBuffer(key, term.c_str(), term.size());
```

- **风险等级**: 中（前缀编码是全局约定，变更会破坏兼容性；代码里无版本化迁移机制证据）
- **STATUS**: IMPLEMENTED

### BR-Idx-02 DocumentID 不能为 0

- **Rule ID**: BR-Idx-02
- **规则名称**: 写入时 DocumentID 禁止为 0
- **规则描述**: 写入入口在构造 key 前检查 `new_document.ID() == 0` 并将文档状态置错，批次返回失败。
- **前置条件**: `IndexWriter::InnerWriteDocuments` 被调用；`documents` 含 `DocumentUpdater`，其 `New()` 已设置 ID。
- **后置条件**: 对于 ID=0 的文档，`DocumentUpdater::Status()` 被设置为 `kDocumentIDCanNotZero`；`ok=false` 导致整体返回 `false`。
- **边界条件**: 同一批次多个文档：只要有任一不满足，整体 `bool ok` 会被置 `false`（详见“批次失败传播规则”）。
- **错误处理**: `du->Status().SetStatus(kDocumentIDCanNotZero, "...")`。
- **调用链**: `IndexWriter::*Documents` → `IndexWriter::InnerWriteDocuments`
- **源码证据**:

```239:247:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_writer.cpp
du->SetUpdateType(mode);
Document &new_document = du->New();
if (new_document.ID() == 0) {
  du->Status().SetStatus(kDocumentIDCanNotZero,
                         "document id can not be zero.");
  ok = false;
}
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Idx-03 存储列族（ColumnFamily）枚举与含义

- **Rule ID**: BR-Idx-03
- **规则名称**: StorageColumnType 固定顺序与含义
- **规则描述**: 存储层以 `StorageColumnType` 枚举区分 stored/inverted/docvalue/meta/dictionary 以及 paxos 相关列；枚举注释要求“不改变顺序”。
- **前置条件**: 使用 `VirtualDB`/`WriteBuffer` 时需要指定 `StorageColumnType`。
- **后置条件**: 写入/读取均以列族+key 作为定位。
- **边界条件**: **UNKNOWN**（新增列族时对旧数据兼容策略）。
- **错误处理**: 无直接错误处理（属于全局约定）。
- **调用链**:
  - 写入：`DocumentWriter::WriteStoredField/WriteInvertedIndex/WriteDocValue` → `WriteBuffer::{Put,Merge,Delete}`
  - 查询：`BooleanWeight::GetScorer`/`PrefixWeight::GetScorer` → `VirtualDB::{MultiGet,NewIterator}`
- **源码证据**:

```53:71:/home/ubuntu/wwsearch-recontruction/wwsearch/include/storage_type.h
// WARNING:
// DO NOT CHANGE ORDER
// IF ADD NEW COLUMN,MUST CHECK CERTIAN'S GETALL ROUTINE.
kStoredFieldColumn = 0,
kInvertedIndexColumn = 1,
kDocValueColumn = 2,
kMetaColumn = 3,
kDictionaryColumn = 4,
// ...
kMaxColumn = 8
```

- **风险等级**: 中
- **STATUS**: IMPLEMENTED

### BR-Idx-04 倒排 key prefix + term 直接拼接（无长度编码）

- **Rule ID**: BR-Idx-04
- **规则名称**: EncodeInvertedKey 直接追加 term bytes
- **规则描述**: 倒排 key 为 `business_type + partition_set + field_id + term_bytes`，term 部分无额外分隔/长度字段。
- **前置条件**: term 为字节串（`std::string`）。
- **后置条件**: `DecodeInvertedKey` 将剩余部分全部视为 term。
- **边界条件**: term 可以为空串（代码允许 `AppendBuffer(..., size=0)`；PrefixQuery/DropTable 中有用 `term=""` 的调用）。
- **错误处理**: `DecodeInvertedKey` 仅校验 `inverted_key.size() < 10` 返回 false。
- **调用链**: `CodecImpl::{EncodeInvertedKey,DecodeInvertedKey}`
- **源码证据**:

```79:100:/home/ubuntu/wwsearch-recontruction/wwsearch/src/codec_impl.cpp
AppendFixed8(key, table.business_type);
AppendFixed64(key, table.partition_set);
AppendFixed8(key, field_id);
AppendBuffer(key, term.c_str(), term.size());
// ...
RemoveFixed8(key, *business_type);
RemoveFixed64(key, *partition_set);
RemoveFixed8(key, *field_id);
*term = key.ToString();
```

- **风险等级**: 中（prefix/seek 的边界依赖 term 拼接语义；若 term 包含任意字节，扫描逻辑需谨慎）
- **STATUS**: IMPLEMENTED

## 2. BR-Field-xx（字段与 flag 规则）

### BR-Field-01 字段 flag 位定义

- **Rule ID**: BR-Field-01
- **规则名称**: kIndexFieldFlag 位掩码定义
- **规则描述**: 字段行为由 `kIndexFieldFlag` 位掩码控制：tokenize / store / docvalue / suffix / inverted index / not-store-invert-terms。
- **前置条件**: `IndexFieldFlag::flag_` 由调用方设置（或通过 Set* 方法设置）。
- **后置条件**: 下游写入/序列化/倒排构建会读取对应 flag。
- **边界条件**: flag 组合冲突未在此处显式约束（例如 Store 与 DocValue 的关系）。
- **错误处理**: 无显式错误码；属于行为开关。
- **调用链**: `IndexFieldFlag` → `IndexField::EncodeToStoreField` / `DocumentWriter::{RunTokenizer,WriteDocValue,WriteInvertedIndex}`
- **源码证据**:

```80:87:/home/ubuntu/wwsearch-recontruction/wwsearch/include/index_field.h
kTokenizeFieldFlag = 1 << 0,
kStoreFieldFlag = 1 << 1,
kDocValueFieldFlag = 1 << 2,
kSuffixBuildFlag = 1 << 3,
kInvertIndexFieldFlag = 1 << 4,
kNotStoreInvertTermFieldFlag = 1 << 5
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Field-02 StoredField 序列化规则（flag=0）

- **Rule ID**: BR-Field-02
- **规则名称**: StoreDocument（stored field）包含 terms（可选）与值（按 flag）
- **规则描述**: 文档序列化到 stored-field（`flag=0`）时：
  - field meta 总是写入（id/flag/type）；
  - value 仅在 `IndexFieldFlag::StoredField()` 为 true 时写入（string_value 或 numeric_value）；
  - terms 在 `flag=0` 且 `NotStoreInvertTerm==false` 时写入；
  - suffix_len 在非 0 时写入。
- **前置条件**: `Document::SerializeToBytes(buffer, 0)` 被调用；每个 `IndexField` 已填充 meta 与值/terms。
- **后置条件**: 生成 `lsmsearch::StoreDocument` protobuf 字节串。
- **边界条件**:
  - 若 `NotStoreInvertTerm` 打开，则 terms 不写入 protobuf（即使 terms 已存在）。
  - 若 `SuffixBuild` 打开且 pb 未携带 suffix_len，则反序列化默认 suffix_len=5（见 BR-Field-04）。
- **错误处理**: `SerializeToString` 返回 false 会向上返回失败；上层写入会设置 `kSerializeErrorStatus`。
- **调用链**: `DocumentWriter::WriteStoredField` → `Document::SerializeToBytes(flag=0)` → `IndexField::EncodeToStoreField(flag=0)` → protobuf `SerializeToString`
- **源码证据**:

```72:92:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document.cpp
lsmsearch::StoreDocument document;
document.set_document_id(this->document_id_);
for (auto field : this->fields_) {
  // docvalue special-case...
  ret = field->EncodeToStoreField(document.add_fields(), 0);
}
ret = document.SerializeToString(&buffer);
```

```141:191:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_field.cpp
field->set_field_id(this->field_id_);
field->set_field_flag(this->field_flag_.Flag());
field->set_field_type(this->field_type_);
// need_value depends on StoredField()/DocValue()
// store invert terms when flag==0 and NotStoreInvertTerm()==false
```

- **风险等级**: 中（stored-field 是否携带 terms 影响“更新时 old terms 来源”；见 BR-Upd-xx）
- **STATUS**: IMPLEMENTED

### BR-Field-03 DocValue 序列化规则（flag=1，仅 DocValue 字段）

- **Rule ID**: BR-Field-03
- **规则名称**: DocValue 仅包含 DocValue 字段（不包含 terms）
- **规则描述**: `Document::SerializeToBytes(buffer, 1, have_field)` 仅序列化 `field->Flag().DocValue()==true` 的字段；`IndexField::EncodeToStoreField(flag=1)` 只在 `DocValue()` 为 true 时写入 value，且不会写入 terms。
- **前置条件**: `DocumentWriter::WriteDocValue` 调用 `BuildDocValue` 生成 docvalue 文档。
- **后置条件**: `have_field` 反映是否存在至少一个 docvalue 字段；若无字段，上层可能删除旧 docvalue。
- **边界条件**: 若 `have_field==false` 且旧文档存在 DocValue 字段，则触发 `kDocValueColumn` 删除（见 BR-Field-05）。
- **错误处理**: 序列化失败设置 `kSerializeErrorStatus`。
- **调用链**: `DocumentWriter::WriteDocValue` → `Document::BuildDocValue` → `Document::SerializeToBytes(flag=1,have_field)` → `WriteBuffer::Put/Delete`
- **源码证据**:

```61:69:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document.cpp
for (IndexField *field : document.Fields()) {
  if (field->Flag().DocValue()) {
    IndexField *new_field = new IndexField;
    new_field->CopyFrom(*field);
    this->fields_.push_back(new_field);
  }
}
```

```72:88:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document.cpp
if (1 == flag && field->Flag().DocValue()) {
  ret = field->EncodeToStoreField(document.add_fields(), 1);
  have_field = true;
}
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Field-04 SuffixBuild 默认 suffix_len=5（当缺失时）

- **Rule ID**: BR-Field-04
- **规则名称**: SuffixBuild 反序列化默认 suffix_len=5
- **规则描述**: 从 pb 反序列化时，如果字段 `SuffixBuild()==true` 且 pb 未携带 suffix_len 或解析后 suffix_len==0，则将 suffix_len 置为 5（注释标记“couldn't change this value”）。
- **前置条件**: `IndexField::DecodeFromStoreField` 被调用，且 field_flag_ 含 `kSuffixBuildFlag`。
- **后置条件**: `IndexField::suffix_len`_ 至少为 5。
- **边界条件**: 若 pb 中 `suffix_len` 存在则使用 pb 值。
- **错误处理**: 无。
- **调用链**: `Document::DeSerializeFromByte` → `IndexField::DecodeFromStoreField`
- **源码证据**:

```228:235:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_field.cpp
if (this->field_flag_.SuffixBuild()) {
  if (field->has_suffix_len()) {
    this->suffix_len_ = field->suffix_len();
  }
  if (this->suffix_len_ == 0) {
    this->suffix_len_ = 5 /*Default suffix len, couldn't change this value*/;
  }
}
```

- **风险等级**: 中（固定默认值会影响倒排展开与查询；若期望可配置需额外实现）
- **STATUS**: IMPLEMENTED

### BR-Field-05 DocValue 列在无字段时的删除行为

- **Rule ID**: BR-Field-05
- **规则名称**: DocValue 无字段时删除旧值（条件性）
- **规则描述**: 写 docvalue 时，如果新 docvalue 文档 `have_field==false`，会扫描旧文档字段是否存在 `DocValue()`；若存在则对 `kDocValueColumn` 进行 Delete（避免保留陈旧 docvalue）。
- **前置条件**: `DocumentWriter::WriteDocValue` 被调用；`du->NeedMergeDocValue()` 可能导致合并旧 docvalue 字段。
- **后置条件**: `need_delete_old==true` 时执行 `write_buffer.Delete(kDocValueColumn, key)`。
- **边界条件**: 删除动作依赖“旧文档 fields 是否包含 DocValue flag”，而不是旧 docvalue value 是否存在。
- **错误处理**: Delete 返回的 `SearchStatus` 会写回 `du->Status()` 并可能中断批次。
- **调用链**: `DocumentWriter::UpdateDocuments` → `WriteDocValue`
- **源码证据**:

```558:584:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
if (new_docvalue_document.SerializeToBytes(value, 1, have_field)) {
  if (have_field) {
    du->Status() = write_buffer.Put(kDocValueColumn, document_key, value);
  } else {
    bool need_delete_old = false;
    for (auto& old_field : old_document.Fields()) {
      if (old_field->Flag().DocValue()) { need_delete_old = true; break; }
    }
    if (need_delete_old) {
      du->Status() = write_buffer.Delete(kDocValueColumn, document_key);
    }
  }
}
```

- **风险等级**: 中（以“旧文档字段 flag”驱动删除，依赖 stored-field 中能正确恢复 old_document）
- **STATUS**: IMPLEMENTED

## 3. BR-Add-xx / BR-Upd-xx / BR-AoU-xx / BR-Replace-xx / BR-Del-xx（写入行为规则）

### BR-Add-01 AddDocuments 仅允许“文档不存在”写入

- **Rule ID**: BR-Add-01
- **规则名称**: AddDocuments 前置存在性检查
- **规则描述**: Add 模式下对 `kStoredFieldColumn` MultiGet；若文档已存在（`!DocumentNotExist()`），则将该文档置错并使批次失败。
- **前置条件**: 调用 `IndexWriter::AddDocuments`，且 `mode==kDocumentAddType`。
- **后置条件**: 已存在文档：`documents[i]->Status()` 设置为 `kDocumentExistStatus` 或透传 `multi_status[i]`；整体 `ok=false`。
- **边界条件**: 多文档批次：只要任一文档存在，整体 `bool` 返回失败（且对未出错文档会设置“batch other error”见 BR-Write-03）。
- **错误处理**: per-document 状态码 + 批次失败。
- **调用链**: `IndexWriter::AddDocuments` → `InnerWriteDocuments` → `VirtualDB::MultiGet(kStoredFieldColumn)` → `UpdateDocumetStatus(mode=Add)` → `DocumentWriter::UpdateDocuments`（仅在 ok=true 时执行）
- **源码证据**:

```108:118:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_writer.cpp
if (kDocumentAddType == mode) {
  if (!multi_status[i].DocumentNotExist()) {
    ok = false;
    if (multi_status[i].OK()) {
      documents[i]->Status().SetStatus(kDocumentExistStatus,
                                       "Document exist before add");
    } else {
      documents[i]->Status() = multi_status[i];
    }
  }
}
```

- **风险等级**: 中（Add 的语义依赖 `DocumentNotExist()` 的实现与存储层一致性）
- **STATUS**: IMPLEMENTED

### BR-Upd-01 UpdateDocuments 需要 old document 解码成功才能继续

- **Rule ID**: BR-Upd-01
- **规则名称**: UpdateDocuments 解码 old stored-field 与 old docvalue（条件性）
- **规则描述**: Update 模式下：若 MultiGet 返回 OK，则必须 `Old().DeSerializeFromByte(stored_bytes)` 成功，否则设置 `kSerializeErrorStatus` 并使批次失败；若 docvalue 存在则还会解码 OldDocValue。
- **前置条件**: `mode==kDocumentUpdateType`。
- **后置条件**: 解码失败：`documents[i]->Status().SetStatus(kSerializeErrorStatus, ...)` 且 `ok=false`。
- **边界条件**: docvalue 解码仅当 `multi_docvalue_status[i].DocumentExist()` 为 true。
- **错误处理**: `kSerializeErrorStatus`。
- **调用链**: `IndexWriter::UpdateDocuments` → `InnerWriteDocuments` → `MultiGet` → `UpdateDocumetStatus(mode=Update)`
- **源码证据**:

```119:142:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_writer.cpp
if (kDocumentUpdateType == mode) {
  if (!multi_status[i].OK()) { ok = false; documents[i]->Status() = multi_status[i]; continue; }
  if (!documents[i]->Old().DeSerializeFromByte(document_values[i].c_str(),
                                               document_values[i].size())) {
    ok = false;
    documents[i]->Status().SetStatus(kSerializeErrorStatus,
                                     "decode document error");
  }
  if (ok && multi_docvalue_status[i].DocumentExist()) {
    if (!documents[i]->OldDocValue().DeSerializeFromByte(...)) {
      ok = false;
      documents[i]->Status().SetStatus(kSerializeErrorStatus,
                                       "decode document error");
    }
  }
}
```

- **风险等级**: 中（更新强依赖 stored-field 能被解析；一旦 stored-field 损坏会阻断更新）
- **STATUS**: IMPLEMENTED

### BR-Upd-02 Update/AddOrUpdate 的“未更新字段保留”规则（stored field）

- **Rule ID**: BR-Upd-02
- **规则名称**: MergeOldField：新文档缺失字段则拷贝旧字段
- **规则描述**: 在非 Delete/Replace 的写入模式下，会把 old_document 中新文档没有的字段复制到 new_document。
- **前置条件**: `DocumentWriter::UpdateDocuments` 中 `MergeOldField` 被执行，且 `du->UpdateType()!=Delete && !=Replace`。
- **后置条件**: new_document 至少包含 old_document 的所有字段（按 field_id 去重：如果 new 已有则跳过）。
- **边界条件**: 该合并发生在 tokenizer 之后、写入 stored-field 之前。
- **错误处理**: 无显式错误；函数返回 `SearchStatus` 但当前实现中未设置错误。
- **调用链**: `IndexWriter::InnerWriteDocuments(ok)` → `DocumentWriter::UpdateDocuments` → `MergeOldField` → `WriteStoredField`
- **源码证据**:

```805:824:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
if (du->UpdateType() == kDocumentDeleteType ||
    du->UpdateType() == kDocumentReplaceType) {
  continue;
}
for (IndexField* field : old_document.Fields()) {
  if (nullptr == new_document.FindField(field->ID())) {
    new_document.AddField()->CopyFrom(*field);
  }
}
```

- **风险等级**: 中（字段级保留会影响写入语义；但是否符合“UpdateDocuments”对外契约需以更上层文档/调用方确证）
- **STATUS**: IMPLEMENTED

### BR-AoU-01 AddOrUpdateDocuments 的分支：不存在视为 OK，存在则解码 old 并继续

- **Rule ID**: BR-AoU-01
- **规则名称**: AddOrUpdate 的存在性处理
- **规则描述**: AddOrUpdate 模式下：若 MultiGet 返回 `kDocumentNotExistStatus` 则“继续”（视为可新增）；若 OK 则解码 old 文档用于后续合并与倒排差分。
- **前置条件**: `mode==kDocumentAddOrUpdateType`。
- **后置条件**: 不存在：不设置错误；存在：`Old().DeSerializeFromByte` 必须成功。
- **边界条件**: docvalue 处理与 Update 类似（存在则解码 OldDocValue）。
- **错误处理**: 非 NotExist 且非 OK 的错误会透传到 `documents[i]->Status()` 并批次失败。
- **调用链**: `IndexWriter::AddOrUpdateDocuments` → `InnerWriteDocuments` → `UpdateDocumetStatus(mode=AddOrUpdate)`
- **源码证据**:

```144:174:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_writer.cpp
if (kDocumentAddOrUpdateType == mode) {
  if (multi_status[i].GetCode() == kDocumentNotExistStatus) {
    continue;
  }
  if (!multi_status[i].OK()) { ok = false; documents[i]->Status() = multi_status[i]; continue; }
  if (!documents[i]->Old().DeSerializeFromByte(...)) {
    ok = false;
    documents[i]->Status().SetStatus(kSerializeErrorStatus,
                                     "decode old document error");
  }
  // docvalue decode when multi_docvalue_status[i].DocumentExist()
}
```

- **风险等级**: 中（AddOrUpdate 的一致性/原子性/并发冲突处理 **未在此处出现锁或事务语义**，见 BR-AoU-02）
- **STATUS**: IMPLEMENTED（仅指该分支逻辑存在）

### BR-AoU-02 AddOrUpdate 原子性 / race condition / lock 机制

- **Rule ID**: BR-AoU-02
- **规则名称**: AddOrUpdate 并发一致性保证
- **规则描述**: **STATUS: UNKNOWN**。在当前代码可见范围内，AddOrUpdate 使用 `MultiGet` 获取旧值并在用户态构建 `WriteBatch` 后 `DB::Write`，未见显式锁/compare-and-swap/事务 DB 的证据。
- **前置条件**: 多线程/多进程并发对同一 `(TableID, DocumentID)` 写入。
- **后置条件**: **UNKNOWN**（是否会发生 lost update 取决于上层调用序列与 RocksDB merge/put 覆盖语义，不能仅凭函数名推断）。
- **边界条件**: **UNKNOWN**。
- **错误处理**: **UNKNOWN**。
- **调用链**: `IndexWriter::InnerWriteDocuments` → `VirtualDB::MultiGet` → `DocumentWriter::UpdateDocuments` → `VirtualDBRocksImpl::FlushBuffer` → `rocksdb::DB::Write(WriteOptions(), WriteBatch)`
- **源码证据**:

```584:598:/home/ubuntu/wwsearch-recontruction/wwsearch/src/virtual_db_rocks.cpp
auto s = this->db_->Write(rocksdb::WriteOptions(), buffer->write_batch_);
```

- **需要动态验证的位置**:
  - 并发写入同一文档：观察 stored-field Put 覆盖、inverted-index Merge 合并顺序与结果（候选点：`rocksdb::DB::Write` 调用前后，或通过 UT/压测复现）。
- **风险等级**: 高（并发语义缺失会直接影响正确性，但这里无法静态证实）
- **STATUS**: UNKNOWN

### BR-Replace-01 ReplaceDocuments 不进行 MergeOldField（字段全量语义的一部分证据）

- **Rule ID**: BR-Replace-01
- **规则名称**: Replace 模式跳过 MergeOldField
- **规则描述**: `MergeOldField` 明确跳过 `kDocumentReplaceType`；因此 replace 不会把 old_document 中缺失字段补回到 new_document。
- **前置条件**: `mode==kDocumentReplaceType`，且 `DocumentWriter::UpdateDocuments` 执行 `MergeOldField`。
- **后置条件**: new_document 保持调用方设置的字段集合（不会自动补齐旧字段）。
- **边界条件**: Replace 仍会读取 old_document（`UpdateDocumetStatus` 中 Replace 分支会在 old 存在时解码；不存在也允许继续），并会在 `WriteInvertedIndex` 使用 old/new terms 做差分（见 BR-IndexUpdate-01）。
- **错误处理**: old 解码失败同样设置 `kSerializeErrorStatus` 并批次失败（当 old 存在且 decode 失败时）。
- **调用链**: `IndexWriter::ReplaceDocuments` → `InnerWriteDocuments` → `DocumentWriter::UpdateDocuments` → `MergeOldField(skip)` → `WriteStoredField/WriteInvertedIndex/WriteDocValue`
- **源码证据**:

```810:813:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
// delete or replace not need merge
if (du->UpdateType() == kDocumentDeleteType ||
    du->UpdateType() == kDocumentReplaceType) {
  continue;
}
```

- **风险等级**: 中（“replace semantics”是否还要求清理旧索引需结合倒排差分与 tombstone 机制；见 BR-Replace-02 / BR-Del-xx）
- **STATUS**: PARTIAL（只证实“不会合并旧字段”；是否“全量覆盖”的完整语义需更多证据）

### BR-Del-01 DeleteDocuments 写入路径：stored-field Delete + docvalue 条件 Delete + inverted-index tombstone Merge

- **Rule ID**: BR-Del-01
- **规则名称**: DeleteDocuments 的物理删除与倒排 tombstone
- **规则描述**: Delete 模式会：
  - `WriteStoredField` 对 stored-field key 执行 `Delete`；
  - `WriteDocValue` 仅在旧文档存在 DocValue 字段时删除 `kDocValueColumn`；
  - `WriteInvertedIndex` 不从新文档收集 terms（跳过 new），但会从 old 文档收集 terms，并对“只存在于 old”的 term 写入 `DocumentStateDelete` 的 doclist operand，通过 `WriteBuffer::Merge(kInvertedIndexColumn, key, value)` 写入（即 tombstone 写入路径）。
- **前置条件**: `du->UpdateType()==kDocumentDeleteType` 且 old 文档能成功解码（否则无法获得 old terms）。
- **后置条件**: stored/docvalue 可能被物理删除；倒排通过 merge 写入 delete 状态。
- **边界条件**:
  - 若 stored-field 中没有保存 terms（例如 `NotStoreInvertTerm`），则 old terms 可能为空，导致倒排 tombstone 无法生成（是否会造成“倒排未清理”需动态或更深证据；此处不推断）。
- **错误处理**: 任一 WriteBuffer 操作失败会设置 status 并中止批次。
- **调用链**: `IndexWriter::DeleteDocuments` → `InnerWriteDocuments` → `DocumentWriter::UpdateDocuments` → `WriteStoredField/Delete` + `WriteDocValue/Delete` + `WriteInvertedIndex/Merge(delete-state)` → `VirtualDBRocksImpl::FlushBuffer(DB::Write)`
- **源码证据**:

```504:506:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
} else {
  du->Status() = write_buffer.Delete(kStoredFieldColumn, document_key);
}
```

```590:602:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
} else {
  bool need_delete_old = false;
  for (auto& old_field : old_document.Fields()) {
    if (old_field->Flag().DocValue()) { need_delete_old = true; break; }
  }
  if (need_delete_old) {
    du->Status() = write_buffer.Delete(kDocValueColumn, document_key);
  }
}
```

```630:705:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
// delete operation ... do not need insert terms in invert index.
if (!du->Delete()) { /* collect new terms */ }
// old terms always collected
for (auto field : du->Old().Fields()) { /* collect old terms */ }
```

```713:744:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
if (term.second == 1 || term.second == 2) {
  DocumentState s =
      term.second == 1 ? kDocumentStateOK : kDocumentStateDelete;
  doc_list->AddDocID(du->New().ID(), s);
  status = write_buffer.Merge(kInvertedIndexColumn, key, value);
}
```

- **风险等级**: 高（删除依赖 old terms；且倒排为 tombstone 语义而非立即物理清理）
- **STATUS**: IMPLEMENTED

### BR-IndexUpdate-01 倒排更新为“差分 Merge”（只对新增或删除的 term 写入）

- **Rule ID**: BR-Upd-03
- **规则名称**: 倒排更新只对差分 term 执行 Merge
- **规则描述**: `WriteInvertedIndex` 汇总 new/old terms 并打标：
  - new-only → flag=1（写入 OK）
  - old-only → flag=2（写入 Delete）
  - new&old → flag=3（不写入，注释“delete but add again,so do nothing”）
- **前置条件**: old/new 文档的 terms 集合均可获得（old 依赖 stored-field 反序列化）。
- **后置条件**: 仅对 flag==1 或 flag==2 的 term 写入 merge operand。
- **边界条件**:
  - delete 操作跳过 new terms 汇总，仅使用 old terms → 生成删除 tombstone。
  - suffix build 会将 term 展开为多个 suffix_term 后参与差分。
- **错误处理**: `write_buffer.Merge` 失败直接返回 error status。
- **调用链**: `DocumentWriter::WriteInvertedIndex` → `CodecImpl::EncodeInvertedKey` → `DocListWriterCodec::SerializeToBytes` → `WriteBuffer::Merge(kInvertedIndexColumn, ...)` → `VirtualDBRocksImpl::FlushBuffer`
- **源码证据**:

```630:669:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
if (!du->Delete()) { /* new terms -> term_match[term] |= 1 */ }
// old terms -> term_match[term] |= 1<<1
```

```706:746:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
if (term.second == 1 || term.second == 2) { /* merge */ }
// else delete but add again,so do nothing.
```

- **风险等级**: 中
- **STATUS**: IMPLEMENTED

### BR-Write-03 批次失败传播规则（部分失败导致其余文档置 kOtherDocumentErrorStatus）

- **Rule ID**: BR-Write-03
- **规则名称**: batch documents 中任一失败 → 其余 OK 文档置“批次未完成”
- **规则描述**: 若 `InnerWriteDocuments` 最终 `ok==false`，会遍历 `documents`，对仍为 OK 的文档设置 `kOtherDocumentErrorStatus`，提示“Some other document meet error in batch documents”。
- **前置条件**: 批次中存在至少一个错误，且部分文档状态仍为 OK。
- **后置条件**: 这些文档被标记为批次失败（即使自身未出错）。
- **边界条件**: 无。
- **错误处理**: `SearchStatus::SetStatus(kOtherDocumentErrorStatus, ...)`
- **调用链**: `IndexWriter::InnerWriteDocuments`
- **源码证据**:

```309:318:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_writer.cpp
if (!ok) {
  for (auto du : documents) {
    if (du->Status().OK()) {
      du->Status().SetStatus(
          kOtherDocumentErrorStatus,
          "Operation not finish,Some other document meet error in batch "
          "documents,Please check other document");
    }
  }
}
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Write-04 持久化边界规则：FlushBuffer / store_buffer

- **Rule ID**: BR-Write-04
- **规则名称**: 写入批次的“提交点”是 VirtualDB::FlushBuffer（或返回 store_buffer）
- **规则描述**: `DocumentWriter::UpdateDocuments` 在 `status.OK()` 后：
  - 若 `store_buffer == nullptr`：调用 `vdb->FlushBuffer(write_buffer)`；
  - 否则：`*store_buffer = write_buffer->Data()`（不 flush）。
- **前置条件**: `WriteStoredField/WriteInvertedIndex/WriteDocValue/...` 全部成功，且 write batch 未超限。
- **后置条件**: RocksDB 路径下 `FlushBuffer` 将 `WriteBatch` 通过 `DB::Write(WriteOptions(), batch)` 持久化。
- **边界条件**:
  - `store_buffer` 非空且已有内容时会用 `NewWriteBuffer(store_buffer)` 进行“从已有 batch 恢复”的构造（见 `WriteBufferRocksImpl` 注释）。
- **错误处理**: FlushBuffer 出错则将该 status 传播到文档状态（见 `UpdateDocuments` 中 reset status 逻辑，需在规则细化中引用）。
- **调用链**: `IndexWriter::InnerWriteDocuments` → `DocumentWriter::UpdateDocuments` → `VirtualDBRocksImpl::FlushBuffer` → `rocksdb::DB::Write`
- **源码证据**:

```89:112:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document_writer.cpp
if (nullptr == store_buffer) {
  status = vdb->FlushBuffer(write_buffer);
} else {
  *store_buffer = write_buffer->Data();
}
```

```584:598:/home/ubuntu/wwsearch-recontruction/wwsearch/src/virtual_db_rocks.cpp
auto s = this->db_->Write(rocksdb::WriteOptions(), buffer->write_batch_);
```

```28:35:/home/ubuntu/wwsearch-recontruction/wwsearch/src/write_buffer_rocks.cpp
// WARNING: write_buffer must be a valid RocksDB::WriteBatch
if (nullptr != write_buffer && !write_buffer->empty()) {
  this->write_batch_ = new rocksdb::WriteBatch(*write_buffer);
} else {
  this->write_batch_ = new rocksdb::WriteBatch();
}
```

- **风险等级**: 中（store_buffer 语义要求调用方遵循“WriteBatch bytes”协议；否则注释提示可能 corruption）
- **STATUS**: IMPLEMENTED

## 4. BR-Query-xx（查询行为规则：DoQuery）

### BR-Query-01 DoQuery 的执行主链（Weight→Scorer→Collector）

- **Rule ID**: BR-Query-01
- **规则名称**: DoQuery 查询执行链
- **规则描述**: `Searcher::DoQuery` 创建 snapshot+context，然后 `query.CreateWeight` 构建 Weight，`weight->GetScorer` 构建 Scorer；迭代 `scorer->Iterator()` 将 docid 推给 `TopNCollector`；最终产出 docid 列表。
- **前置条件**: 调用方提供 `Query&`（如 `BooleanQuery/AndQuery/OrQuery/PrefixQuery`）并配置 `IndexConfig`（含 `VirtualDB`）。
- **后置条件**: 输出 `std::list<DocumentID>`；资源释放 snapshot。
- **边界条件**: `scorer==nullptr` 时返回 `kScorerErrorStatus`（若 context 未先置错）。
- **错误处理**: collector status / context status 透出。
- **调用链**: `Searcher::DoQuery` → `VirtualDB::NewSnapshot` → `Query::CreateWeight` → `Weight::GetScorer` → `TopNCollector::{Collect,Finish,GetAndClearMatchDocs}` → `VirtualDB::ReleaseSnapshot`
- **源码证据**:

```24:90:/home/ubuntu/wwsearch-recontruction/wwsearch/src/searcher.cpp
VirtualDBSnapshot *snapshot = vdb->NewSnapshot();
SearchContext context(table, vdb, snapshot, config_);
weight = query.CreateWeight(&context, false, 0);
scorer = weight->GetScorer(&context);
TopNCollector collector(...);
DocIdSetIterator &doc_lists = scorer->Iterator();
while (...) { collector.Collect(doc_lists.DocID(), doc_lists.FieldId()); doc_lists.NextDoc(); }
collector.Finish();
collector.GetAndClearMatchDocs(docs);
vdb->ReleaseSnapshot(snapshot);
```

- **风险等级**: 中
- **STATUS**: IMPLEMENTED

### BR-Query-02 Filter 执行顺序与 min_match_filter_num 规则

- **Rule ID**: BR-Query-02
- **规则名称**: Filter 顺序为 vector 遍历顺序，按 match_count 阈值通过
- **规则描述**: `TopNCollector::MatchFilter` 遍历 `*filter`_，对每条 filter 调 `rule->Match(find_field)`，累加 match_count；最终 `match_count >= min_match_filter_num`_ 才通过。代码中**未短路**（失败不立即 return）。
- **前置条件**: DoQuery 传入 `filter!=nullptr`。
- **后置条件**: filter 命中数不足则 doc 被过滤掉。
- **边界条件**:
  - `min_match_filter_num_==0` 时，构造器会将其置为 `filter->size()`（即“全匹配”语义），但该语义是否为最终对外约定需以调用方确证。
- **错误处理**: filter 自身为纯 bool；字段缺失时 `find_field==nullptr` 会传入 `Match(nullptr)`，多数 filter 直接返回 false。
- **调用链**: `Searcher::DoQuery` → `TopNCollector::InnerPurge` → `GetDocValue` → `MatchFilter` → 各 `Filter::Match`
- **源码证据**:

```110:115:/home/ubuntu/wwsearch-recontruction/wwsearch/include/collector_top.h
if (nullptr != filter) {
  if (0 == min_match_filter_num_ ||
      min_match_filter_num_ > filter->size()) {
    min_match_filter_num_ = filter->size();
  }
}
```

```309:333:/home/ubuntu/wwsearch-recontruction/wwsearch/src/collector_top.cpp
for (auto rule : *this->filter_) {
  auto find_field = document->FindField(rule->GetFieldID());
  if (!rule->Match(find_field)) {
    // return false;
  } else {
    match_count++;
  }
}
if (match_count >= min_match_filter_num_) return true;
return false;
```

- **风险等级**: 中（未短路可能导致 filter 有副作用时行为不直观；但当前 Filter 实现未见副作用）
- **STATUS**: IMPLEMENTED

### BR-Query-03 Sort 机制（priority_queue + SortCondition 链）

- **Rule ID**: BR-Query-03
- **规则名称**: Sorter 逐 SortCondition 比较，默认按 DocumentID
- **规则描述**: `Sorter` 在 `sort_condictions_==nullptr` 时按 `lhs->ID() > rhs->ID()`；否则逐 `SortCondition` 比较，若都无法区分则回退到 `lhs->ID() > rhs->ID()`。
- **前置条件**: DoQuery 传入 `sorter!=nullptr` 或 null。
- **后置条件**: `TopNCollector` 使用 priority_queue 维护 top-n。
- **边界条件**: `NumericSortCondition`/`StringSortCondition` 在字段缺失或类型不匹配时，按“缺字段的排后/按 docid 兜底”的规则比较（见实现）。
- **错误处理**: 无显式错误码。
- **调用链**: `TopNCollector` → `PriorityQueue(topN_docs_)` → `Sorter::operator()`
- **源码证据**:

```146:165:/home/ubuntu/wwsearch-recontruction/wwsearch/include/sorter.h
if (nullptr == sort_condictions_) return lhs->ID() > rhs->ID();
for (auto sc : *sort_condictions_) {
  auto lhs_field = lhs->FindField(sc->GetID());
  auto rhs_field = rhs->FindField(sc->GetID());
  auto c1 = sc->Greater(lhs->ID(), lhs_field, rhs->ID(), rhs_field);
  auto c2 = sc->Greater(rhs->ID(), rhs_field, lhs->ID(), lhs_field);
  if (c1 && c2) { continue; }
  else if (c1) { return true; }
  else { return false; }
}
return lhs->ID() > rhs->ID();
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Query-04 Pagination 规则（top_n=offset+limit + 最终 offset 丢弃）

- **Rule ID**: BR-Query-04
- **规则名称**: 通过 top_n 与 GetAndClearMatchDocs 做分页
- **规则描述**: `TopNCollector` 以 `top_n_ = offset + limit` 控制 heap 容量；最终 `GetAndClearMatchDocs` 先输出 `top_n`_ 个，再执行 `offset_` 次删除 docs.front()。
- **前置条件**: DoQuery 提供 offset/limit。
- **后置条件**: 输出 docs 数量最多为 limit（当 match 足够时）。
- **边界条件**: 若 offset > 实际匹配数，结果可能为空；未设置错误码。
- **错误处理**: 无。
- **调用链**: `Searcher::DoQuery` → `TopNCollector` → `GetAndClearMatchDocs`
- **源码证据**:

```98:103:/home/ubuntu/wwsearch-recontruction/wwsearch/include/collector_top.h
top_n_(offset + limit),
offset_(offset),
limit_(limit),
```

```109:123:/home/ubuntu/wwsearch-recontruction/wwsearch/src/collector_top.cpp
while (topN_docs_.size() != 0 && top_n_ > 0) {
  docs.push_front(this->topN_docs_.top()->ID());
  delete this->topN_docs_.top();
  this->topN_docs_.pop();
  --top_n_;
}
while (offset_ > 0 && docs.size() > 0) {
  docs.remove(docs.front());
  --offset_;
}
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Query-05 Query parse / tokenizer / multi-field query / partition routing

- **Rule ID**: BR-Query-05
- **规则名称**: Query 解析与路由能力
- **规则描述**: **STATUS: UNKNOWN / PARTIAL**。当前仓库中 `Searcher::DoQuery` 的输入是 `Query&`（调用方显式构造 Query 对象），未见 query-string parser；tokenizer 的 `BuildTerms` 在 query 主链中未见调用；DoQuery 接受单个 `TableID`，未见跨分区 fanout/merge。
- **前置条件**: 调用方期望传入 query 文本或跨表查询。
- **后置条件**: **UNKNOWN**（不在 DoQuery 路径内）。
- **边界条件**: 仅能确认 `PrefixQuery/BooleanQuery/AndQuery/OrQuery` 组合（属于 Query 对象构造层，而非 parse）。
- **错误处理**: **UNKNOWN**。
- **源码证据**:

```51:59:/home/ubuntu/wwsearch-recontruction/wwsearch/include/searcher.h
SearchStatus DoQuery(
    const TableID &table, Query &query, size_t offset, size_t limit,
    std::vector<Filter *> *filter, std::vector<SortCondition *> *sorter,
    std::list<DocumentID> &docs, ...);
```

```36:39:/home/ubuntu/wwsearch-recontruction/wwsearch/src/searcher.cpp
SearchContext context(table, vdb, snapshot, config_);
```

- **需要动态验证的位置**:
  - 若存在上层路由：查找仓库外调用点或额外组件；当前 repo 内可从 `example/example.cpp` 与 `unittest/*query`* 仅看到“直接构造 Query 对象”。
- **风险等级**: 中
- **STATUS**: UNKNOWN（对 parse/tokenize/routing）

## 5. BR-Partition-xx（分表/路由规则）

### BR-Partition-01 TableID 结构定义

- **Rule ID**: BR-Partition-01
- **规则名称**: TableID = business_type(uint8) + partition_set(uint64)
- **规则描述**: `TableID` 由 `business_type` 与 `partition_set` 构成，并提供 `PrintToStr()`。
- **前置条件**: 调用方设置这两个字段。
- **后置条件**: 作为 codec key 前缀的一部分（见 BR-Idx-01）。
- **边界条件**: 路由策略不在此结构中表达（仅保存标识）。
- **错误处理**: 无。
- **调用链**: 用户调用 → 写入/查询 key 编码
- **源码证据**:

```40:49:/home/ubuntu/wwsearch-recontruction/wwsearch/include/storage_type.h
typedef struct TableID {
  uint8_t business_type;
  uint64_t partition_set;
  std::string PrintToStr() const { ... }
} TableID;
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### BR-Partition-02 partition routing strategy

- **Rule ID**: BR-Partition-02
- **规则名称**: 跨 partition/table 的路由策略
- **规则描述**: **STATUS: UNKNOWN**。当前 `Searcher::DoQuery` 与 `IndexWriter::*Documents` 均以单个 `TableID` 操作；未见内部路由器对多个 `TableID` 执行 fanout/merge。
- **缺失原因**: repo 内缺少“路由/聚合”层代码（可能在上层服务中）。
- **需要动态验证的位置**: 上层调用点；或通过 `Searcher::ScanBusinessType` 枚举分区集合后自行调用 DoQuery（该策略不在 DoQuery 内实现）。
- **风险等级**: 中
- **STATUS**: UNKNOWN

## 6. CFG-*（配置规则：RocksDB / cache / WAL / compaction / thread pool）

### CFG-01 RocksDB 参数来源：VDBParams

- **Rule ID**: CFG-01
- **规则名称**: RocksDB 参数通过 `VDBParams` 提供默认值
- **规则描述**: `VDBParams` 定义了 mmseg 字典路径/实例数以及 RocksDB compaction、WAL、buffer、cache 等参数的默认值；`VirtualDBRocksImpl::InitDBOptions()` 将这些值写入 `rocksdb::Options`。
- **前置条件**: 使用 `VirtualDBRocksImpl(&params, ...)` 并调用 `Open()` 触发 options 初始化。
- **后置条件**: RocksDB 实例使用这些 Options。
- **边界条件**: 某些字段为 0 表示“不设置”（如 `rocks_db_block_cache_bytes`、`rocks_db_max_open_files`）。
- **错误处理**: **UNKNOWN**（Open 失败如何传播取决于 `VirtualDBRocksImpl::Open()` 的完整实现，需补充读取更多行）。
- **调用链**: `DefaultIndexWrapper::Open(use_rocksdb=true)` → `VirtualDBRocksImpl::Open` → `InitDBOptions`
- **源码证据**:

```32:85:/home/ubuntu/wwsearch-recontruction/wwsearch/include/virtual_db.h
typedef struct VDBParams {
  std::string path;
  std::string mmseg_dict_dir_ = "./";
  uint64_t mmseg_instance_num_ = 20;
  // rocksdb ... max_total_wal_size/db_write_buffer_size/num_levels/...
  uint64_t rocks_max_total_wal_size = 100 << 20;
  // ...
  rocksdb::CompressionType rocks_compression = rocksdb::kSnappyCompression;
  Codec* codec_;
  uint32_t max_doc_list_num_ = 1000000;
} VDBParams;
```

```671:699:/home/ubuntu/wwsearch-recontruction/wwsearch/src/virtual_db_rocks.cpp
options_.OptimizeLevelStyleCompaction();
options_.create_if_missing = true;
options_.create_missing_column_families = true;
options_.max_subcompactions = params_->rocks_max_subcompactions;
options_.allow_concurrent_memtable_write = params_->rocks_allow_concurrent_memtable_write;
options_.max_log_file_size = params_->rocks_max_log_file_size;
options_.log_file_time_to_roll = params_->rocks_log_file_time_to_roll;
options_.keep_log_file_num = params_->rocks_keep_log_file_num;
options_.max_manifest_file_size = params_->rocks_max_manifest_file_size;
options_.level0_file_num_compaction_trigger = params_->rocks_level0_file_num_compaction_trigger;
options_.level0_slowdown_writes_trigger = params_->rocks_level0_slowdown_writes_trigger;
options_.level0_stop_writes_trigger = params_->rocks_level0_stop_writes_trigger;
```

- **风险等级**: 中
- **STATUS**: IMPLEMENTED（参数赋值存在；是否完全覆盖需求取决于更多 options 代码）

### CFG-02 单次写入 WAL 选项（disableWAL/sync）

- **Rule ID**: CFG-02
- **规则名称**: 写入使用默认 WriteOptions（未显式配置 WAL）
- **规则描述**: `VirtualDBRocksImpl::FlushBuffer` 在无 write_queue 的路径下调用 `db_->Write(rocksdb::WriteOptions(), batch)`，未见显式设置 `disableWAL`/`sync` 等字段。
- **前置条件**: `write_queue_==nullptr`。
- **后置条件**: 使用 RocksDB 默认 WriteOptions。
- **边界条件**: write_queue_ 分支的 WriteOptions 配置 **UNKNOWN**（需进一步实现证据）。
- **错误处理**: RocksDB Status 非 ok 时设置 `kRocksDBErrorStatus` 并带 `s.getState()`。
- **调用链**: `DocumentWriter::UpdateDocuments` → `VirtualDBRocksImpl::FlushBuffer` → `rocksdb::DB::Write`
- **源码证据**:

```584:592:/home/ubuntu/wwsearch-recontruction/wwsearch/src/virtual_db_rocks.cpp
auto s = this->db_->Write(rocksdb::WriteOptions(), buffer->write_batch_);
if (!s.ok()) {
  status.SetStatus(kRocksDBErrorStatus, s.getState());
}
```

- **风险等级**: 中（WAL/sync 策略不透明；但不能推断 durability 级别）
- **STATUS**: IMPLEMENTED

### CFG-03 异步写队列（DbRocksWriteQueue）启用规则

- **Rule ID**: CFG-03
- **规则名称**: RocksDB 写队列 write_queue_ 的启用与语义
- **规则描述**: **STATUS: UNKNOWN / PARTIAL**。接口 `DbRocksWriteQueue` 存在，`VirtualDBRocksImpl::FlushBuffer` 有 write_queue_ 分支，但默认 wrapper 传入 nullptr；且 `virtual_db_rocks_write_queue.cpp` 在当前 repo 里为空实现（需进一步确认）。
- **前置条件**: 构造 `VirtualDBRocksImpl` 时传入非空 `write_queue`_。
- **后置条件**: FlushBuffer 走 `write_queue_->Write(...)`。
- **边界条件**: 线程模型/队列长度/backpressure 均未知。
- **错误处理**: 由 `WriteQueue::Write` 返回的 `SearchStatus` 决定。
- **调用链**: `VirtualDBRocksImpl::FlushBuffer` → `DbRocksWriteQueue::Write`
- **源码证据**:

```586:596:/home/ubuntu/wwsearch-recontruction/wwsearch/src/virtual_db_rocks.cpp
if (!write_queue_) {
  // db_->Write(...)
} else {
  VirtualDBRocksWriteOption write_options;
  status = write_queue_->Write(this, &write_options, write_buffer);
}
```

```25:36:/home/ubuntu/wwsearch-recontruction/wwsearch/include/virtual_db_rocks_write_queue.h
class DbRocksWriteQueue {
  virtual SearchStatus Write(VirtualDB *db, VirtualDBWriteOption *options,
                             WriteBuffer *write_buffer) = 0;
};
```

```40:45:/home/ubuntu/wwsearch-recontruction/wwsearch/src/index_wrapper.cpp
vdb_ = new VirtualDBRocksImpl(&this->params_, nullptr);
```

- **风险等级**: 中
- **STATUS**: UNKNOWN（队列实现缺失）

## 7. CG-*（代码生成/序列化规则：protobuf）

### CG-01 Protobuf schema：search_store.proto → search_store.pb.h

- **Rule ID**: CG-01
- **规则名称**: StoreDocument/StoreIndexField schema 由 proto 生成
- **规则描述**: `include/search_store.pb.h` 明确为 protoc 生成文件，source 为 `search_store.proto`；其中包含 `lsmsearch::StoreDocument`、`StoreIndexField` 等消息类型。
- **前置条件**: 编译期已有 protoc 生成物（pb.h/pb.cc，当前仓库含 pb.h；pb.cc 是否编入库见 CMake `include/*.cc` 的 glob，实际需要确认 pb.cc 是否位于 include/）。
- **后置条件**: C++ 序列化/反序列化使用 pb Message API。
- **边界条件**: protoc 版本约束在 pb.h 内（2.4.x）。
- **错误处理**: pb Parse/Serialize 返回 bool，调用方检查并设置 `kSerializeErrorStatus`（见 CG-02）。
- **调用链**: `Document::{SerializeToBytes,DeSerializeFromByte}` / `IndexField::{EncodeToStoreField,DecodeFromStoreField}` → protobuf
- **源码证据**:

```1:3:/home/ubuntu/wwsearch-recontruction/wwsearch/include/search_store.pb.h
// Generated by the protocol buffer compiler.  DO NOT EDIT!
// source: search_store.proto
```

- **风险等级**: 低
- **STATUS**: IMPLEMENTED

### CG-02 文档序列化规则（pb SerializeToString/ParseFromArray）

- **Rule ID**: CG-02
- **规则名称**: Document 使用 StoreDocument protobuf 序列化
- **规则描述**: `Document::SerializeToBytes` 构造 `lsmsearch::StoreDocument`，添加 fields 后 `SerializeToString(&buffer)`；反序列化使用 `ParseFromArray(buffer, len)` 并逐 field `DecodeFromStoreField`。
- **前置条件**: `Document` fields 已构造完成（包括 field_flag、terms 等）。
- **后置条件**: stored-field/docvalue 的 value 为 protobuf bytes。
- **边界条件**: Parse 失败则返回 false，调用链上层会将状态置为 `kSerializeErrorStatus`（在 `IndexWriter::UpdateDocumetStatus`）。
- **错误处理**: Parse/Serialize bool 返回；上层转为 `SearchStatus`。
- **调用链**: `DocumentWriter::WriteStoredField/WriteDocValue` → `Document::SerializeToBytes` → protobuf；读取路径 `IndexWriter::UpdateDocumetStatus` / `Searcher::InnerGetFields` → `Document::DeSerializeFromByte` → protobuf
- **源码证据**:

```72:92:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document.cpp
lsmsearch::StoreDocument document;
document.set_document_id(this->document_id_);
// add_fields() + EncodeToStoreField(...)
ret = document.SerializeToString(&buffer);
```

```95:108:/home/ubuntu/wwsearch-recontruction/wwsearch/src/document.cpp
lsmsearch::StoreDocument document;
ret = document.ParseFromArray(buffer, buffer_len);
this->document_id_ = document.document_id();
for (size_t i = 0; i < document.fields_size(); i++) {
  ret = this->AddField()->DecodeFromStoreField(&(document.fields(i)));
}
```

- **风险等级**: 中（stored-field 中 terms 的存在性影响更新/删除的倒排差分能力）
- **STATUS**: IMPLEMENTED

## 8. 规则缺口与 UNKNOWN 汇总

- **UNKNOWN-01 架构分析基线缺失**: `docs/architecture_analysis.md` 不存在，需要补做或用本文件中的调用链作为基线。
- **UNKNOWN-02 并发一致性/原子性**: 写入在用户态 `MultiGet` + `WriteBatch` 构造后提交，无显式锁；需动态验证并发冲突表现（见 BR-AoU-02）。
- **UNKNOWN-03 Query parse/tokenize**: DoQuery 不对 query text 做解析，tokenizer 的 `BuildTerms` 未出现在 query 主链；若上层有 parser 需在 repo 外确认（见 BR-Query-05）。
- **UNKNOWN-04 write_queue_**: 写队列接口存在但实现缺失/不可证实（见 CFG-03）。

## 9. 风险区域（仅基于可见源码）

- **高风险**:
  - Delete/Update 对倒排差分依赖 old terms：若 stored-field 未保存 terms（`kNotStoreInvertTermFieldFlag`），则倒排更新/删除可能缺失 tombstone（本点只描述依赖关系，不推断最终结果）。证据：`WriteInvertedIndex` 的 old terms 来自 `du->Old().Fields()`，而 old 来自 pb 反序列化；pb terms 写入受 `NotStoreInvertTerm` 控制。
  - 并发写入语义未知（见 BR-AoU-02）。
- **中风险**:
  - `store_buffer` 必须为 RocksDB WriteBatch bytes（注释警告 corruption）。
  - ColumnFamily 枚举要求不改变顺序（兼容风险）。

