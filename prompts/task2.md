# 任务：为 wwsearch 生成可运行的集成测试与测试剧本

你是一名资深测试开发工程师。

目标：

基于：

* `/work/docs/business_rules_wwsearch.md`
* `/work/wwsearch/`

生成：

1. 测试剧本文档
2. Python 集成测试代码
3. 必要的 helper 封装
4. 并实际运行验证测试

---

# Docker 执行环境（必须遵守）

所有命令：

必须通过以下方式执行：

```bash
sudo docker exec ww bash -lc '<command>'
```

示例：

```bash
sudo docker exec ww bash -lc 'cd /work && ls'
```

⚠️ 禁止：

* 在宿主机直接执行命令
* 使用宿主机路径
* 假设当前 shell 已在容器内
* 使用 `/workspace/...`

后续所有路径：
必须基于：

```text
/work
```

---

# 第一阶段：环境探测（必须先执行）

先真实检查环境。

必须执行：

```bash
sudo docker exec ww bash -lc 'cd /work && ls'
sudo docker exec ww bash -lc 'find /work/wwsearch/build -type f'
sudo docker exec ww bash -lc 'find /work/wwsearch -name "*example*"'
sudo docker exec ww bash -lc 'find /work/wwsearch -name "*ut*"'
sudo docker exec ww bash -lc 'find /work/wwsearch/build -name "*.so"'
```

目标：

确认：

* 可执行文件位置
* 动态库位置
* example 程序
* unittest 程序
* build 输出目录

⚠️ 禁止：

* 假设 executable 名称
* 假设 build 目录结构
* 假设 .so 文件存在

---

# 第二阶段：分析真实 API 用法

重点分析：

* `/work/wwsearch/example/example.cpp`
* `/work/wwsearch/unittest/`

目标：

识别：

1. AddDocuments 调用方式
2. UpdateDocuments 调用方式
3. DeleteDocuments 调用方式
4. ReplaceDocuments 调用方式
5. Query 调用方式
6. 配置文件格式
7. 数据目录初始化方式
8. 返回码语义

必须优先复用官方 example 的调用模式。

⚠️ 禁止：

* 编造 CLI 参数
* 假设 stdout 格式
* 假设 API 返回值

若 example 不支持完整测试：
允许编写 helper。

---

# 第三阶段：生成测试剧本文档

生成：

```text
/work/docs/test_scenarios_wwsearch.md
```

要求：

1. 覆盖：

   * BR-Add
   * BR-Upd
   * BR-AoU
   * BR-Replace
   * BR-Del
   * BR-Query

2. 每个场景必须包含：

| 字段                |
| ----------------- |
| 场景ID              |
| 关联规则ID            |
| 测试目标              |
| Preconditions     |
| Steps             |
| Expected Result   |
| Validation Method |

3. 场景必须覆盖：

* 正向
* 负向
* 边界
* 重复 ID
* 空字段
* 大文本
* 不存在文档
* 非法参数
* 多字段查询
* 删除后查询

4. 对：

   * UNKNOWN
   * PARTIAL

规则：

使用 Expected Failure 标记。

---

# 第四阶段：生成 Python 集成测试

生成：

```text
/work/tests/integration_test_wwsearch.py
```

必要时生成：

```text
/work/tests/wwsearch_helper.py
```

要求：

1. 使用 unittest
2. 每个测试使用独立数据目录
3. 自动清理临时文件
4. 不依赖网络
5. 不依赖第三方 Python 库
6. 优先使用 subprocess 调用官方 example

---

# 极其重要：禁止伪测试

禁止：

* mock 测试
* assert 0 == 0
* 空测试
* 不调用 wwsearch 的“伪集成测试”
* fake helper
* 编造返回值

每个测试必须：

1. 真正创建索引
2. 真正写入文档
3. 真正执行查询
4. 真正校验结果

---

# helper 约束

如果 example 不适合直接测试：

允许创建：

```text
/work/tests/wwsearch_helper.py
```

封装：

* add_document
* update_document
* delete_document
* replace_document
* query_document

但 helper 必须：

* 基于真实 executable
* 基于真实 stdout/stderr
* 不允许 fake return

---

# 第五阶段：实际运行测试（必须执行）

必须真实运行：

```bash
sudo docker exec ww bash -lc '
cd /work &&
export LD_LIBRARY_PATH=/work/wwsearch/build/lib:$LD_LIBRARY_PATH &&
python3 tests/integration_test_wwsearch.py -v
'
```

必须：

1. 修复 import/path 问题
2. 修复动态库问题
3. 修复数据目录问题
4. 修复 example 参数问题
5. 修复权限问题

直到：

* 测试通过
* 或合理标记：

  * expectedFailure
  * skip

---

# 输出文件

必须生成：

```text
/work/docs/test_scenarios_wwsearch.md
/work/tests/integration_test_wwsearch.py
```

可选：

```text
/work/tests/wwsearch_helper.py
```

---

# 测试代码要求

每个测试方法：

必须：

* 名称清晰
* 包含 docstring
* 标注 TS ID
* 标注 Rule ID

示例：

```python
def test_add_document_success(self):
    '''
    TS-ww-Add-01
    BR-Add-01
    '''
```

---

# 严格约束

禁止：

* 假设 CLI 参数
* 假设返回值
* 编造接口
* 生成无法运行的代码
* 只生成文档不运行
* 不验证 executable 是否存在

若某功能无法自动化：

使用：

* @unittest.skip
* @unittest.expectedFailure

并说明真实原因。

---

# 最终目标

最终必须能够执行：

```bash
sudo docker exec ww bash -lc '
cd /work &&
export LD_LIBRARY_PATH=/work/wwsearch/build/lib:$LD_LIBRARY_PATH &&
python3 tests/integration_test_wwsearch.py -v
'
```

并看到：

* 真实调用 wwsearch
* 可运行测试
* 清晰测试结果
* 合理的失败/跳过标记
