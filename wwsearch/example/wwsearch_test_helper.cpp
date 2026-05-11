/*
 * wwsearch_test_helper.cpp
 *
 * 专为集成测试设计的命令行工具，补充 wwsearch_example 不覆盖的写入操作。
 *
 * 用法:
 *   wwsearch_test_helper <db_dir> <op> [args...]
 *
 * 支持的操作:
 *   add        <docid> <field0_text> <field1_uint32> <field2_uint32>
 *   update     <docid> <field0_text> <field1_uint32> <field2_uint32>
 *   addorupdate <docid> <field0_text> <field1_uint32> <field2_uint32>
 *   replace    <docid> <field0_text> <field1_uint32> <field2_uint32>
 *   delete     <docid>
 *   query      <term> [field_id=0]
 *   get        <docid>
 *
 * 字段约定 (与 example.cpp 保持一致):
 *   field 0: 文本字段 (tokenize + suffix + stored + invert + docvalue)
 *   field 1: uint32 过滤字段
 *   field 2: uint32 排序字段
 *
 * 退出码:
 *   0  成功
 *   1  操作失败（输出包含 RESULT:FAIL）
 *   2  参数错误
 *
 * 输出格式 (Python 解析用):
 *   RESULT:OK
 *   RESULT:FAIL <state>
 *   QUERY:MATCH <count>
 *   QUERY:DOCID <id>
 *   GET:FIELD <field_id> <type> <value>
 *   GET:NOTFOUND
 */

 #include <cstdlib>
 #include <iostream>
 #include <string>
 #include <vector>
 
 #include "include/and_query.h"
 #include "include/bool_query.h"
 #include "include/codec_impl.h"
 #include "include/document.h"
 #include "include/index_wrapper.h"
 #include "include/index_writer.h"
 #include "include/logger.h"
 #include "include/query.h"
 #include "include/searcher.h"
 #include "include/storage_type.h"
 #include "include/tokenizer_impl.h"
 #include "include/virtual_db_rocks.h"
 #include "include/weight.h"
 
 // ---- 全局 TableID（与 example.cpp 保持一致）----
 static wwsearch::TableID g_table;
 
 // ---- 构建标准字段 flag ----
 static wwsearch::IndexFieldFlag MakeFlag() {
   wwsearch::IndexFieldFlag flag;
   flag.SetStoredField();
   flag.SetTokenize();
   flag.SetSuffixBuild();
   flag.SetDocValue();
   flag.SetInvertIndex();
   return flag;
 }
 
 // ---- 构建一个文档 ----
 static wwsearch::DocumentUpdater* MakeDocument(
     uint64_t docid,
     const std::string& text,
     uint32_t field1_val,
     uint32_t field2_val) {
   wwsearch::IndexFieldFlag flag = MakeFlag();
   wwsearch::DocumentUpdater* du = new wwsearch::DocumentUpdater();
   wwsearch::Document& doc = du->New();
   doc.SetID(docid);
 
   {
     auto f = doc.AddField();
     f->SetMeta(0, flag);
     f->SetString(text);
   }
   {
     auto f = doc.AddField();
     f->SetMeta(1, flag);
     f->SetUint32(field1_val);
   }
   {
     auto f = doc.AddField();
     f->SetMeta(2, flag);
     f->SetUint32(field2_val);
   }
   return du;
 }
 
 // ---- 打印操作结果 ----
 static int PrintResult(bool success,
                        const std::vector<wwsearch::DocumentUpdater*>& docs) {
   if (success) {
     std::cout << "RESULT:OK" << std::endl;
     return 0;
   } else {
     for (auto du : docs) {
       if (!du->Status().OK()) {
         std::cout << "RESULT:FAIL " << du->Status().GetState() << std::endl;
       }
     }
     // 如果所有 du 状态都 OK（整体 bool=false 但 per-doc OK），也打印 FAIL
     std::cout << "RESULT:FAIL batch_error" << std::endl;
     return 1;
   }
 }
 
 // ====================================================================
 // op: add
 // ====================================================================
 static int OpAdd(wwsearch::DefaultIndexWrapper& indexer,
                  uint64_t docid,
                  const std::string& text,
                  uint32_t f1, uint32_t f2) {
   auto* du = MakeDocument(docid, text, f1, f2);
   std::vector<wwsearch::DocumentUpdater*> docs = {du};
   bool ok = indexer.index_writer_->AddDocuments(g_table, docs);
   int ret = PrintResult(ok, docs);
   delete du;
   return ret;
 }
 
 // ====================================================================
 // op: update
 // ====================================================================
 static int OpUpdate(wwsearch::DefaultIndexWrapper& indexer,
                     uint64_t docid,
                     const std::string& text,
                     uint32_t f1, uint32_t f2) {
   auto* du = MakeDocument(docid, text, f1, f2);
   std::vector<wwsearch::DocumentUpdater*> docs = {du};
   bool ok = indexer.index_writer_->UpdateDocuments(g_table, docs);
   int ret = PrintResult(ok, docs);
   delete du;
   return ret;
 }
 
 // ====================================================================
 // op: addorupdate
 // ====================================================================
 static int OpAddOrUpdate(wwsearch::DefaultIndexWrapper& indexer,
                          uint64_t docid,
                          const std::string& text,
                          uint32_t f1, uint32_t f2) {
   auto* du = MakeDocument(docid, text, f1, f2);
   std::vector<wwsearch::DocumentUpdater*> docs = {du};
   bool ok = indexer.index_writer_->AddOrUpdateDocuments(g_table, docs);
   int ret = PrintResult(ok, docs);
   delete du;
   return ret;
 }
 
 // ====================================================================
 // op: replace
 // ====================================================================
 static int OpReplace(wwsearch::DefaultIndexWrapper& indexer,
                      uint64_t docid,
                      const std::string& text,
                      uint32_t f1, uint32_t f2) {
   auto* du = MakeDocument(docid, text, f1, f2);
   std::vector<wwsearch::DocumentUpdater*> docs = {du};
   bool ok = indexer.index_writer_->ReplaceDocuments(g_table, docs);
   int ret = PrintResult(ok, docs);
   delete du;
   return ret;
 }
 
 // ====================================================================
 // op: delete
 // ====================================================================
 static int OpDelete(wwsearch::DefaultIndexWrapper& indexer, uint64_t docid) {
   // Delete 需要先填充 New() 的 ID，实际 old terms 从 stored-field 读取
   wwsearch::DocumentUpdater* du = new wwsearch::DocumentUpdater();
   du->New().SetID(docid);
   std::vector<wwsearch::DocumentUpdater*> docs = {du};
   bool ok = indexer.index_writer_->DeleteDocuments(g_table, docs);
   int ret = PrintResult(ok, docs);
   delete du;
   return ret;
 }
 
 // ====================================================================
 // op: query  <term> [field_id]
 // ====================================================================
 static int OpQuery(wwsearch::DefaultIndexWrapper& indexer,
                    const std::string& term,
                    int field_id) {
   wwsearch::Searcher searcher(&indexer.Config());
   wwsearch::BooleanQuery query(field_id, term);
 
   std::list<wwsearch::DocumentID> match_docids;
   auto status = searcher.DoQuery(g_table, query, 0, 100,
                                  nullptr, nullptr, match_docids);
   if (!status.OK()) {
     std::cout << "RESULT:FAIL " << status.GetState() << std::endl;
     return 1;
   }
   std::cout << "QUERY:MATCH " << match_docids.size() << std::endl;
   for (auto id : match_docids) {
     std::cout << "QUERY:DOCID " << id << std::endl;
   }
   std::cout << "RESULT:OK" << std::endl;
   return 0;
 }
 
 // ====================================================================
 // op: get  <docid>
 // ====================================================================
 static int OpGet(wwsearch::DefaultIndexWrapper& indexer, uint64_t docid) {
   wwsearch::Searcher searcher(&indexer.Config());
   wwsearch::Document* doc = new wwsearch::Document();
   doc->SetID(docid);
 
   std::vector<wwsearch::Document*> docs = {doc};
   std::vector<wwsearch::SearchStatus> ss;
   auto ret = searcher.GetStoredFields(g_table, docs, ss, nullptr);
 
   int exit_code = 0;
   if (!ret.OK()) {
     std::cout << "GET:NOTFOUND" << std::endl;
     std::cout << "RESULT:FAIL " << ret.GetState() << std::endl;
     exit_code = 1;
   } else if (ss.empty() || !ss[0].OK()) {
     std::cout << "GET:NOTFOUND" << std::endl;
     std::cout << "RESULT:FAIL notfound" << std::endl;
     exit_code = 1;
   } else {
     for (auto field : doc->Fields()) {
       // 输出字段: GET:FIELD <field_id> <type> <value>
       // type: s=string, u=uint32/uint64
       if (field->StringValue().size() > 0) {
         std::cout << "GET:FIELD " << (int)field->ID()
                   << " s " << field->StringValue() << std::endl;
       } else {
         std::cout << "GET:FIELD " << (int)field->ID()
                   << " u " << field->NumericValue() << std::endl;
       }
     }
     std::cout << "RESULT:OK" << std::endl;
   }
 
   delete doc;
   return exit_code;
 }
 
 // ====================================================================
 // main
 // ====================================================================
 int main(int argc, char** argv) {
   if (argc < 3) {
     std::cerr << "Usage: " << argv[0]
               << " <db_dir> <op> [args...]\n"
               << "ops: add update addorupdate replace delete query get\n";
     return 2;
   }
 
   std::string db_dir = argv[1];
   std::string op     = argv[2];
 
   // 初始化 indexer
   wwsearch::DefaultIndexWrapper indexer;
   indexer.DBParams().path = db_dir;
   // 关闭 debug 日志，避免污染 stdout（测试解析用）
   indexer.Config().SetLogLevel(wwsearch::kSearchLogLevelError);
 
   wwsearch::SearchStatus status = indexer.Open(true /*use_rocksdb*/);
   if (!status.OK()) {
     std::cerr << "Open DB failed: " << status.GetState() << std::endl;
     return 2;
   }
 
   // 与 example.cpp 保持一致的 TableID
   g_table.business_type = 1;
   g_table.partition_set = 10000;
 
   // ---- 路由到对应操作 ----
 
   if (op == "add" || op == "update" || op == "addorupdate" || op == "replace") {
     if (argc < 7) {
       std::cerr << "Usage: " << argv[0]
                 << " <db_dir> " << op
                 << " <docid> <field0_text> <field1_uint32> <field2_uint32>\n";
       return 2;
     }
     uint64_t docid = std::stoull(argv[3]);
     std::string text = argv[4];
     uint32_t f1 = (uint32_t)std::stoul(argv[5]);
     uint32_t f2 = (uint32_t)std::stoul(argv[6]);
 
     if (op == "add")          return OpAdd(indexer, docid, text, f1, f2);
     if (op == "update")       return OpUpdate(indexer, docid, text, f1, f2);
     if (op == "addorupdate")  return OpAddOrUpdate(indexer, docid, text, f1, f2);
     if (op == "replace")      return OpReplace(indexer, docid, text, f1, f2);
   }
 
   if (op == "delete") {
     if (argc < 4) {
       std::cerr << "Usage: " << argv[0] << " <db_dir> delete <docid>\n";
       return 2;
     }
     uint64_t docid = std::stoull(argv[3]);
     return OpDelete(indexer, docid);
   }
 
   if (op == "query") {
     if (argc < 4) {
       std::cerr << "Usage: " << argv[0] << " <db_dir> query <term> [field_id]\n";
       return 2;
     }
     std::string term = argv[3];
     int field_id = (argc >= 5) ? std::stoi(argv[4]) : 0;
     return OpQuery(indexer, term, field_id);
   }
 
   if (op == "get") {
     if (argc < 4) {
       std::cerr << "Usage: " << argv[0] << " <db_dir> get <docid>\n";
       return 2;
     }
     uint64_t docid = std::stoull(argv[3]);
     return OpGet(indexer, docid);
   }
 
   std::cerr << "Unknown op: " << op << std::endl;
   return 2;
 }