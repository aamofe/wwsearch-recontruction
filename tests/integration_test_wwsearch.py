import os
import sys
import tempfile
import unittest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from wwsearch_helper import run_wwsearch_example


class WWSearchIntegrationTest(unittest.TestCase):
    def _new_db_dir(self) -> str:
        # Each test uses an independent data directory.
        td = tempfile.TemporaryDirectory(prefix="wwsearch_it_")
        self.addCleanup(td.cleanup)
        return td.name

    def test_add_document_success(self):
        """
        TS-ww-Add-01
        BR-Add-01
        """
        db_dir = self._new_db_dir()
        result = run_wwsearch_example(db_dir)

        self.assertEqual(
            result.returncode,
            0,
            msg=f"example returncode={result.returncode}\nstderr:\n{result.stderr}\nstdout:\n{result.stdout}",
        )
        self.assertIn("After Add Status:", result.stdout)
        self.assertGreaterEqual(result.count_success_statuses(), 3, msg=result.stdout)
        self.assertGreater(result.max_query_match(), 0, msg=result.stdout)

    def test_add_duplicate_id_should_fail(self):
        """
        TS-ww-Add-02
        BR-Add-01
        """
        db_dir = self._new_db_dir()

        r1 = run_wwsearch_example(db_dir)
        self.assertEqual(r1.returncode, 0, msg=r1.stderr)

        r2 = run_wwsearch_example(db_dir)
        # The example prints a banner when Add fails, but still continues running queries.
        # We validate via stdout semantics, not fake return values.
        self.assertTrue(
            r2.has_add_error_banner() or ("Code:Failure" in r2.stdout),
            msg=f"expected duplicate-add failure signal, got:\n{r2.stdout}",
        )

    @unittest.skip("No official CLI for UpdateDocuments; need helper executable or build wwsearch_ut with scriptable entry.")
    def test_update_document_success_and_merge_old_field(self):
        """
        TS-ww-Upd-01
        BR-Upd-01
        BR-Upd-02
        """
        raise NotImplementedError()

    @unittest.skip("No official CLI for AddOrUpdateDocuments; need helper executable or build wwsearch_ut with scriptable entry.")
    def test_add_or_update_document(self):
        """
        TS-ww-AoU-01
        BR-AoU-01
        """
        raise NotImplementedError()

    @unittest.expectedFailure
    @unittest.skip("ReplaceDocuments CLI missing; additionally BR-Replace-01 is PARTIAL and needs more evidence to assert full semantics.")
    def test_replace_document_should_not_merge_old_fields(self):
        """
        TS-ww-Replace-01
        BR-Replace-01
        """
        raise NotImplementedError()

    @unittest.skip("DeleteDocuments CLI missing; need helper executable or build wwsearch_ut with scriptable entry.")
    def test_delete_then_query_should_not_match(self):
        """
        TS-ww-Del-01
        BR-Del-01
        """
        raise NotImplementedError()

    @unittest.expectedFailure
    @unittest.skip("BR-Query-05 is UNKNOWN; repo lacks query-string parser/routing evidence and official executable entry.")
    def test_query_multi_field_expected_failure(self):
        """
        TS-ww-Query-02
        BR-Query-05
        """
        raise NotImplementedError()


if __name__ == "__main__":
    # Keep runtime aligned with user's required command:
    #   cd /work && export LD_LIBRARY_PATH=... && python3 tests/integration_test_wwsearch.py -v
    # The helper also enforces LD_LIBRARY_PATH, but this makes failures clearer.
    os.environ["LD_LIBRARY_PATH"] = "/work/wwsearch/build/lib:" + os.environ.get("LD_LIBRARY_PATH", "")
    unittest.main(verbosity=2)

