"""
wwsearch_helper_v2.py

封装对 wwsearch_example 和 wwsearch_test_helper 的 subprocess 调用。
所有函数返回 RunResult 对象，包含 returncode / stdout / stderr 与便捷解析方法。
"""

import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple


# ============================================================
# 公共基础
# ============================================================

def _default_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = dict(os.environ)
    required = "/work/wwsearch/build/lib"
    ld = env.get("LD_LIBRARY_PATH", "")
    if required not in ld.split(":"):
        env["LD_LIBRARY_PATH"] = required + ((":" + ld) if ld else "")
    if extra:
        env.update(extra)
    return env


def _run(cmd: List[str], timeout_s: int = 30,
         extra_env: Optional[Dict[str, str]] = None) -> "RunResult":
    proc = subprocess.run(
        cmd,
        cwd="/work",
        env=_default_env(extra_env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout_s,
    )
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


# ============================================================
# RunResult：统一结果对象
# ============================================================

class RunResult:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    # ---- example.cpp 专用解析 ----

    def count_success_statuses(self) -> int:
        """统计 stdout 中 'Code:Success' 出现次数"""
        return len(re.findall(r"\bCode:Success\b", self.stdout))

    def has_add_error_banner(self) -> bool:
        return "Add Document return error" in self.stdout

    def max_query_match(self) -> int:
        """从 example.cpp 输出中取最大 match 数，找不到返回 -1"""
        matches = re.findall(r"query:\s*match\s*(\d+)", self.stdout)
        return max((int(x) for x in matches), default=-1)

    # ---- helper 专用解析 ----

    def is_ok(self) -> bool:
        """helper 操作是否成功（含 RESULT:OK 且 returncode==0）"""
        return self.returncode == 0 and "RESULT:OK" in self.stdout

    def is_fail(self) -> bool:
        return "RESULT:FAIL" in self.stdout

    def fail_reason(self) -> str:
        """提取 RESULT:FAIL 后面的原因字符串"""
        m = re.search(r"RESULT:FAIL\s+(.*)", self.stdout)
        return m.group(1).strip() if m else ""

    def query_match_count(self) -> int:
        """从 helper query 输出中取命中数，找不到返回 -1"""
        m = re.search(r"QUERY:MATCH\s+(\d+)", self.stdout)
        return int(m.group(1)) if m else -1

    def query_docids(self) -> List[int]:
        """从 helper query 输出中取所有命中 docid"""
        return [int(x) for x in re.findall(r"QUERY:DOCID\s+(\d+)", self.stdout)]

    def get_fields(self) -> Dict[int, Tuple[str, str]]:
        """
        从 helper get 输出中解析字段。
        返回 {field_id: (type, value)}，type 为 's' 或 'u'。
        """
        result: Dict[int, Tuple[str, str]] = {}
        for m in re.finditer(r"GET:FIELD\s+(\d+)\s+([su])\s+(.*)", self.stdout):
            fid = int(m.group(1))
            ftype = m.group(2)
            fval = m.group(3).strip()
            result[fid] = (ftype, fval)
        return result

    def is_not_found(self) -> bool:
        return "GET:NOTFOUND" in self.stdout

    def __repr__(self) -> str:
        return (f"RunResult(rc={self.returncode}, "
                f"stdout={self.stdout!r:.120}, "
                f"stderr={self.stderr!r:.80})")


# ============================================================
# example.cpp 调用（保持向后兼容）
# ============================================================

# 保留旧名以兼容已有测试
ExampleRunResult = RunResult


def run_wwsearch_example(db_dir: str, timeout_s: int = 30,
                         extra_env: Optional[Dict[str, str]] = None) -> RunResult:
    """运行官方示例程序（Add + Query）"""
    exe = "/work/wwsearch/build/wwsearch_example"
    return _run([exe, db_dir], timeout_s=timeout_s, extra_env=extra_env)


# ============================================================
# test_helper 调用
# ============================================================

_HELPER_EXE = "/work/wwsearch/build/wwsearch_test_helper"


def helper_add(db_dir: str, docid: int, text: str,
               f1: int = 100, f2: int = 1000,
               timeout_s: int = 30) -> RunResult:
    """AddDocuments"""
    return _run([_HELPER_EXE, db_dir, "add",
                 str(docid), text, str(f1), str(f2)],
                timeout_s=timeout_s)


def helper_update(db_dir: str, docid: int, text: str,
                  f1: int = 100, f2: int = 1000,
                  timeout_s: int = 30) -> RunResult:
    """UpdateDocuments"""
    return _run([_HELPER_EXE, db_dir, "update",
                 str(docid), text, str(f1), str(f2)],
                timeout_s=timeout_s)


def helper_addorupdate(db_dir: str, docid: int, text: str,
                       f1: int = 100, f2: int = 1000,
                       timeout_s: int = 30) -> RunResult:
    """AddOrUpdateDocuments"""
    return _run([_HELPER_EXE, db_dir, "addorupdate",
                 str(docid), text, str(f1), str(f2)],
                timeout_s=timeout_s)


def helper_replace(db_dir: str, docid: int, text: str,
                   f1: int = 100, f2: int = 1000,
                   timeout_s: int = 30) -> RunResult:
    """ReplaceDocuments"""
    return _run([_HELPER_EXE, db_dir, "replace",
                 str(docid), text, str(f1), str(f2)],
                timeout_s=timeout_s)


def helper_delete(db_dir: str, docid: int,
                  timeout_s: int = 30) -> RunResult:
    """DeleteDocuments"""
    return _run([_HELPER_EXE, db_dir, "delete", str(docid)],
                timeout_s=timeout_s)


def helper_query(db_dir: str, term: str, field_id: int = 0,
                 timeout_s: int = 30) -> RunResult:
    """DoQuery（BooleanQuery）"""
    return _run([_HELPER_EXE, db_dir, "query", term, str(field_id)],
                timeout_s=timeout_s)


def helper_get(db_dir: str, docid: int,
               timeout_s: int = 30) -> RunResult:
    """GetStoredFields"""
    return _run([_HELPER_EXE, db_dir, "get", str(docid)],
                timeout_s=timeout_s)