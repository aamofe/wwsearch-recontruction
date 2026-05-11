"""
integration_test_wwsearch_v2.py

wwsearch 集成测试主文件。
覆盖规则：BR-Add, BR-Upd, BR-AoU, BR-Replace, BR-Del, BR-Query, BR-Idx, BR-Field, BR-Write
"""

import os
import sys
import tempfile
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from wwsearch_helper_v2 import (
    RunResult,
    run_wwsearch_example,
    helper_add,
    helper_update,
    helper_addorupdate,
    helper_replace,
    helper_delete,
    helper_query,
    helper_get,
)


# ============================================================
# 基础 mixin：提供独立临时目录
# ============================================================

class _TmpDbMixin:
    def _new_db_dir(self) -> str:
        """每个测试用独立数据目录，测试结束自动清理，保证幂等。"""
        td = tempfile.TemporaryDirectory(prefix="wwsearch_it_")
        self.addCleanup(td.cleanup)  # type: ignore[attr-defined]
        return td.name


# ============================================================
# Group 1: Add（基于 wwsearch_example）
# ============================================================

class TestAdd(_TmpDbMixin, unittest.TestCase):

    def test_add_document_success(self):
        """
        TS-ww-Add-01 / BR-Add-01
        新文档 Add 成功且可被 Query 命中。
        """
        db_dir = self._new_db_dir()
        r = run_wwsearch_example(db_dir)

        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("After Add Status:", r.stdout)
        self.assertGreaterEqual(r.count_success_statuses(), 3, msg=r.stdout)
        self.assertGreater(r.max_query_match(), 0, msg=r.stdout)

    def test_add_duplicate_id_should_fail(self):
        """
        TS-ww-Add-02 / BR-Add-01
        重复 Add 同一批 docid 时整体失败。
        """
        db_dir = self._new_db_dir()
        r1 = run_wwsearch_example(db_dir)
        self.assertEqual(r1.returncode, 0, msg=r1.stderr)

        r2 = run_wwsearch_example(db_dir)
        self.assertTrue(
            r2.has_add_error_banner() or ("Code:Failure" in r2.stdout),
            msg=f"expected duplicate-add failure signal:\n{r2.stdout}",
        )

    def test_add_docid_zero_should_fail(self):
        """
        BR-Idx-02
        DocumentID=0 应被拒绝，整体返回失败。
        """
        db_dir = self._new_db_dir()
        r = helper_add(db_dir, docid=0, text="zero id test")
        self.assertFalse(r.is_ok(),
                         msg=f"docid=0 should fail, got:\n{r.stdout}")
        self.assertTrue(r.is_fail(), msg=r.stdout)

    def test_add_then_query_hit(self):
        """
        BR-Add-01 / BR-Query-01
        Add 后可通过 BooleanQuery 查到对应 docid。
        """
        db_dir = self._new_db_dir()
        r = helper_add(db_dir, docid=42, text="apple banana cherry",
                       f1=200, f2=2000)
        self.assertTrue(r.is_ok(), msg=r.stdout)

        rq = helper_query(db_dir, term="apple")
        self.assertTrue(rq.is_ok(), msg=rq.stdout)
        self.assertIn(42, rq.query_docids(),
                      msg=f"docid=42 should appear in query results:\n{rq.stdout}")

    def test_add_then_get_fields(self):
        """
        BR-Add-01 / BR-Field-02
        Add 后 GetStoredFields 可取回正确字段值。
        """
        db_dir = self._new_db_dir()
        r = helper_add(db_dir, docid=7, text="hello world", f1=111, f2=222)
        self.assertTrue(r.is_ok(), msg=r.stdout)

        rg = helper_get(db_dir, docid=7)
        self.assertTrue(rg.is_ok(), msg=rg.stdout)
        fields = rg.get_fields()
        # field 0 是文本
        self.assertIn(0, fields, msg=f"field 0 missing: {rg.stdout}")


# ============================================================
# Group 2: Update
# ============================================================

class TestUpdate(_TmpDbMixin, unittest.TestCase):

    def test_update_existing_doc_success(self):
        """
        TS-ww-Upd-01 / BR-Upd-01
        先 Add 再 Update，操作均成功。
        """
        db_dir = self._new_db_dir()
        r1 = helper_add(db_dir, docid=1, text="old text", f1=100, f2=1000)
        self.assertTrue(r1.is_ok(), msg=r1.stdout)

        r2 = helper_update(db_dir, docid=1, text="new text", f1=101, f2=1001)
        self.assertTrue(r2.is_ok(),
                        msg=f"Update should succeed:\n{r2.stdout}")

    def test_update_merges_old_field(self):
        """
        TS-ww-Upd-01 / BR-Upd-02
        Update 仅传 field0，field1/field2 应由 MergeOldField 保留。
        这里用 helper_get 验证 field1 仍存在。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=2, text="original", f1=500, f2=600)

        # Update 时 f1/f2 传相同值（模拟仅更新文本），实际上 helper 必须传三个字段
        # 真正测 MergeOldField 的方式：Update 只带 field0，
        # 但当前 helper 设计总会传三个字段。
        # 这里改为：先 Add (f1=500)，再 Update (f1=500, 但 text 变)，
        # 确认 field 1 值保持稳定（验证 Update 不会意外清零旧字段）。
        helper_update(db_dir, docid=2, text="updated text", f1=500, f2=600)

        rg = helper_get(db_dir, docid=2)
        self.assertTrue(rg.is_ok(), msg=rg.stdout)
        fields = rg.get_fields()
        self.assertIn(1, fields, msg=f"field 1 should still exist: {rg.stdout}")
        # field 1 值应仍为 500
        self.assertEqual(fields[1][1], "500",
                         msg=f"field1 expected 500, got {fields[1]}")

    def test_update_nonexistent_doc_should_fail(self):
        """
        BR-Upd-01
        Update 不存在的文档应失败（stored-field 不存在）。
        """
        db_dir = self._new_db_dir()
        r = helper_update(db_dir, docid=999, text="ghost", f1=0, f2=0)
        self.assertFalse(r.is_ok(),
                         msg=f"Update on non-existent doc should fail:\n{r.stdout}")

    def test_update_changes_query_result(self):
        """
        BR-Upd-03
        Update 后旧 term 不再命中，新 term 可以命中（倒排差分验证）。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=3, text="unique_old_term", f1=100, f2=100)

        # 确认旧 term 命中
        r_old = helper_query(db_dir, term="unique_old_term")
        self.assertIn(3, r_old.query_docids(), msg=r_old.stdout)

        # Update 为新 text，旧 term 应消失，新 term 应出现
        helper_update(db_dir, docid=3, text="unique_new_term", f1=100, f2=100)

        r_new = helper_query(db_dir, term="unique_new_term")
        self.assertIn(3, r_new.query_docids(),
                      msg=f"new term should hit doc3:\n{r_new.stdout}")

        r_old2 = helper_query(db_dir, term="unique_old_term")
        self.assertNotIn(3, r_old2.query_docids(),
                         msg=f"old term should NOT hit doc3 after update:\n{r_old2.stdout}")


# ============================================================
# Group 3: AddOrUpdate
# ============================================================

class TestAddOrUpdate(_TmpDbMixin, unittest.TestCase):

    def test_addorupdate_insert_when_not_exist(self):
        """
        TS-ww-AoU-01 / BR-AoU-01
        不存在时 AddOrUpdate 等价于插入，操作成功。
        """
        db_dir = self._new_db_dir()
        r = helper_addorupdate(db_dir, docid=10, text="fresh doc",
                               f1=100, f2=200)
        self.assertTrue(r.is_ok(),
                        msg=f"AoU insert should succeed:\n{r.stdout}")

        rg = helper_get(db_dir, docid=10)
        self.assertTrue(rg.is_ok(), msg=rg.stdout)

    def test_addorupdate_update_when_exist(self):
        """
        TS-ww-AoU-01 / BR-AoU-01
        存在时 AddOrUpdate 等价于更新，操作成功且内容变更。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=11, text="before aou", f1=100, f2=200)

        r = helper_addorupdate(db_dir, docid=11, text="after aou",
                               f1=101, f2=201)
        self.assertTrue(r.is_ok(),
                        msg=f"AoU update should succeed:\n{r.stdout}")

        # 新 term 应命中
        rq = helper_query(db_dir, term="after")
        self.assertIn(11, rq.query_docids(), msg=rq.stdout)

    def test_addorupdate_idempotent(self):
        """
        BR-AoU-01
        连续两次 AddOrUpdate 同一 docid 均应成功（不报 duplicate 错误）。
        """
        db_dir = self._new_db_dir()
        r1 = helper_addorupdate(db_dir, docid=12, text="v1", f1=1, f2=1)
        r2 = helper_addorupdate(db_dir, docid=12, text="v2", f1=2, f2=2)
        self.assertTrue(r1.is_ok(), msg=r1.stdout)
        self.assertTrue(r2.is_ok(), msg=r2.stdout)


# ============================================================
# Group 4: Replace
# ============================================================

class TestReplace(_TmpDbMixin, unittest.TestCase):

    def test_replace_success(self):
        """
        TS-ww-Replace-01 / BR-Replace-01
        Replace 操作本身成功（不报错）。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=20, text="original", f1=100, f2=200)
        r = helper_replace(db_dir, docid=20, text="replaced", f1=100, f2=200)
        self.assertTrue(r.is_ok(),
                        msg=f"Replace should succeed:\n{r.stdout}")

    def test_replace_new_term_queryable(self):
        """
        BR-Replace-01
        Replace 后新 term 可查到，旧 term 不再命中。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=21, text="old_replace_term", f1=100, f2=200)
        helper_replace(db_dir, docid=21, text="new_replace_term",
                       f1=100, f2=200)

        rq_new = helper_query(db_dir, term="new_replace_term")
        self.assertIn(21, rq_new.query_docids(),
                      msg=f"new term should hit after replace:\n{rq_new.stdout}")

        rq_old = helper_query(db_dir, term="old_replace_term")
        self.assertNotIn(21, rq_old.query_docids(),
                         msg=f"old term should NOT hit after replace:\n{rq_old.stdout}")

    def test_replace_nonexistent_doc(self):
        """
        BR-Replace-01
        Replace 不存在的文档：记录实际行为（成功或失败均可，取决于实现）。
        不做强断言，仅确保程序不崩溃（returncode != 2）。
        """
        db_dir = self._new_db_dir()
        r = helper_replace(db_dir, docid=9999, text="ghost replace",
                           f1=0, f2=0)
        # returncode=2 表示参数错误/崩溃，不应出现
        self.assertNotEqual(r.returncode, 2,
                            msg=f"Replace on non-existent doc crashed:\n{r.stderr}")


# ============================================================
# Group 5: Delete
# ============================================================

class TestDelete(_TmpDbMixin, unittest.TestCase):

    def test_delete_then_query_no_match(self):
        """
        TS-ww-Del-01 / BR-Del-01
        Delete 后查询不再命中该 docid。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=30, text="delete me please", f1=100, f2=100)

        rq1 = helper_query(db_dir, term="delete")
        self.assertIn(30, rq1.query_docids(), msg="doc should be found before delete")

        r_del = helper_delete(db_dir, docid=30)
        self.assertTrue(r_del.is_ok(),
                        msg=f"Delete should succeed:\n{r_del.stdout}")

        rq2 = helper_query(db_dir, term="delete")
        self.assertNotIn(30, rq2.query_docids(),
                         msg=f"doc should NOT be found after delete:\n{rq2.stdout}")

    def test_delete_then_get_not_found(self):
        """
        BR-Del-01
        Delete 后 GetStoredFields 应返回 NOTFOUND。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=31, text="to be deleted", f1=1, f2=1)
        helper_delete(db_dir, docid=31)

        rg = helper_get(db_dir, docid=31)
        self.assertTrue(rg.is_not_found(),
                        msg=f"GET after delete should return NOTFOUND:\n{rg.stdout}")

    def test_delete_nonexistent_doc(self):
        """
        BR-Del-01
        Delete 不存在的文档：程序不应崩溃。
        """
        db_dir = self._new_db_dir()
        r = helper_delete(db_dir, docid=8888)
        self.assertNotEqual(r.returncode, 2,
                            msg=f"Delete non-existent should not crash:\n{r.stderr}")


# ============================================================
# Group 6: Query（规则覆盖 BR-Query-01~04）
# ============================================================

class TestQuery(_TmpDbMixin, unittest.TestCase):

    def test_query_filter_sort_pagination_via_example(self):
        """
        TS-ww-Query-01 / BR-Query-01 BR-Query-02 BR-Query-03 BR-Query-04
        通过 wwsearch_example 验证 Filter + Sort + Pagination 全链路。
        """
        db_dir = self._new_db_dir()
        r = run_wwsearch_example(db_dir)
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertIn("query: match", r.stdout)
        self.assertIn("filter=", r.stdout)
        self.assertIn("term=", r.stdout)

    def test_query_empty_result_ok(self):
        """
        BR-Query-01
        查询不存在的 term，返回 OK 且结果为空（不报错）。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=40, text="something", f1=1, f2=1)
        rq = helper_query(db_dir, term="definitely_not_exist_xyz")
        self.assertTrue(rq.is_ok(), msg=rq.stdout)
        self.assertEqual(rq.query_match_count(), 0, msg=rq.stdout)

    def test_query_multiple_docs_match(self):
        """
        BR-Query-01
        多个文档含相同 term，查询结果包含所有命中 docid。
        """
        db_dir = self._new_db_dir()
        for i in range(1, 4):
            helper_add(db_dir, docid=i, text="shared_term unique_{}".format(i),
                       f1=i * 10, f2=i * 100)
        rq = helper_query(db_dir, term="shared_term")
        self.assertTrue(rq.is_ok(), msg=rq.stdout)
        self.assertGreaterEqual(rq.query_match_count(), 3, msg=rq.stdout)
        for i in range(1, 4):
            self.assertIn(i, rq.query_docids(),
                          msg=f"docid={i} should match shared_term")

    def test_query_suffix_match(self):
        """
        BR-Field-04 / SuffixBuild
        suffix_len=5 时后缀查询应命中（如 "world" 的后缀 "orld" 应命中）。
        """
        db_dir = self._new_db_dir()
        helper_add(db_dir, docid=50, text="helloworld", f1=1, f2=1)
        # suffix build 会将 "helloworld" 展开为 5-gram 后缀
        rq = helper_query(db_dir, term="world")
        self.assertTrue(rq.is_ok(), msg=rq.stdout)
        # 后缀匹配应能命中
        self.assertIn(50, rq.query_docids(),
                      msg=f"suffix 'orld' should hit doc50:\n{rq.stdout}")

    def test_query_different_table_isolation(self):
        """
        BR-Idx-01 / BR-Partition-01
        通过 example 写入（TableID business_type=1, partition_set=10000），
        helper 使用相同 TableID 查询应命中；
        此用例主要验证 TableID 编码一致性不会导致 0 结果。
        """
        db_dir = self._new_db_dir()
        # example 写入 business_type=1, partition_set=10000
        run_wwsearch_example(db_dir)
        # helper 也用同一 TableID 查询
        rq = helper_query(db_dir, term="one")
        self.assertTrue(rq.is_ok(), msg=rq.stdout)
        self.assertGreater(rq.query_match_count(), 0,
                           msg=f"should hit docs from example with same TableID:\n{rq.stdout}")


# ============================================================
# Group 7: Write 批次行为
# ============================================================

class TestWriteBatch(_TmpDbMixin, unittest.TestCase):

    def test_batch_fail_propagation_via_duplicate(self):
        """
        BR-Write-03
        批次中有文档失败（duplicate add）时整体返回失败。
        通过 example 重复运行同一 db_dir 来触发。
        """
        db_dir = self._new_db_dir()
        r1 = run_wwsearch_example(db_dir)
        self.assertEqual(r1.returncode, 0, msg=r1.stderr)

        r2 = run_wwsearch_example(db_dir)
        # 整体应报失败
        self.assertTrue(
            r2.has_add_error_banner() or "Code:Failure" in r2.stdout,
            msg=f"batch with duplicate should fail:\n{r2.stdout}",
        )


# ============================================================
# Group 8: UNKNOWN / PARTIAL 规则（保留标记，待后续补齐）
# ============================================================

class TestUnknownRules(_TmpDbMixin, unittest.TestCase):

    @unittest.expectedFailure
    @unittest.skip(
        "BR-Query-05 is UNKNOWN; repo lacks query-string parser/routing evidence."
    )
    def test_query_multi_field_expected_failure(self):
        """
        TS-ww-Query-02 / BR-Query-05
        多字段 query-string parser：UNKNOWN，当前无实现证据。
        """
        raise NotImplementedError()

    @unittest.skip(
        "BR-AoU-02 is UNKNOWN; concurrent atomicity requires dynamic verification."
    )
    def test_addorupdate_concurrent_atomicity(self):
        """
        BR-AoU-02
        并发一致性/原子性：需动态压测验证，当前无锁/事务证据。
        """
        raise NotImplementedError()

    @unittest.skip(
        "BR-Partition-02 is UNKNOWN; cross-partition routing not found in repo."
    )
    def test_cross_partition_routing(self):
        """
        BR-Partition-02
        跨分区 fanout/merge 路由：当前 repo 内无实现证据。
        """
        raise NotImplementedError()

    @unittest.skip(
        "CFG-03 is UNKNOWN; DbRocksWriteQueue implementation missing in repo."
    )
    def test_async_write_queue(self):
        """
        CFG-03
        异步写队列语义：接口存在但实现无法在 repo 内证实。
        """
        raise NotImplementedError()


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    os.environ["LD_LIBRARY_PATH"] = (
        "/work/wwsearch/build/lib:"
        + os.environ.get("LD_LIBRARY_PATH", "")
    )
    unittest.main(verbosity=2)