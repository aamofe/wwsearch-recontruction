import os
import re
import subprocess
from typing import Dict, Optional


class ExampleRunResult:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def count_success_statuses(self) -> int:
        return len(re.findall(r"\bCode:Success\b", self.stdout))

    def has_add_error_banner(self) -> bool:
        return "Add Document return error" in self.stdout

    def max_query_match(self) -> int:
        matches = re.findall(r"query:\s*match\s*(\d+)", self.stdout)
        if not matches:
            return -1
        return max(int(x) for x in matches)


def _default_env() -> Dict[str, str]:
    env = dict(os.environ)
    # Per user requirement: LD_LIBRARY_PATH must include /work/wwsearch/build/lib
    # We also allow caller to override/extend.
    ld = env.get("LD_LIBRARY_PATH", "")
    required = "/work/wwsearch/build/lib"
    if required not in ld.split(":"):
        env["LD_LIBRARY_PATH"] = required + ((":" + ld) if ld else "")
    return env


def resolve_example_executable() -> str:
    """
    Resolve the example executable path inside the container filesystem layout.

    Expected location (from CMakeLists): build target name is `wwsearch_example`.
    The repo is mounted at /work.
    """
    return "/work/wwsearch/build/wwsearch_example"


def run_wwsearch_example(db_dir: str, timeout_s: int = 30, extra_env: Optional[Dict[str, str]] = None) -> ExampleRunResult:
    exe = resolve_example_executable()
    env = _default_env()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        [exe, db_dir],
        cwd="/work",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=timeout_s,
    )
    return ExampleRunResult(proc.returncode, proc.stdout, proc.stderr)

