#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$ROOT_DIR"

export PMMA_DISABLE_ENV_AUTOLOAD=1
export PMMA_LLM_ENABLED=0

echo "== PM Method Agent 手动冒烟开始 =="
echo "临时目录: $TMP_DIR"
echo

mkdir -p "$TMP_DIR/.pmma" "$TMP_DIR/notes/sub"
cat > "$TMP_DIR/.pmma/policy.json" <<'EOF'
{
  "runtime_policy": {
    "allowed_read_roots": ["notes"],
    "allowed_write_roots": ["notes"]
  }
}
EOF

printf 'alpha\nbeta\nalpha\n' > "$TMP_DIR/notes/demo.txt"
printf 'nested\nvalue\n' > "$TMP_DIR/notes/sub/nested.txt"

echo "== 列工具 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --list
echo

echo "== 查看 local-text-search 参数 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --describe local-text-search
echo

echo "== 目录枚举 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --format json \
  --tool-name local-directory-list \
  --payload-json '{"workspace_id":"manual-smoke","path":"notes","max_entries":20}'
echo

echo "== 文本搜索 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --format json \
  --tool-name local-text-search \
  --payload-json '{"workspace_id":"manual-smoke","path":"notes","query":"alpha"}'
echo

echo "== 读取文件 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --format json \
  --tool-name local-text-file-read \
  --payload-json '{"workspace_id":"manual-smoke","path":"notes/demo.txt"}'
echo

echo "== 写入文件 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --format json \
  --tool-name local-text-file-write \
  --payload-json '{"workspace_id":"manual-smoke","path":"notes/output.txt","content":"written-from-smoke"}'
echo

echo "== Agent 多轮 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" agent \
  --workspace-id smoke-agent \
  "最近诊所前台老说这里总会漏提醒，我在想是不是该处理一下。"
echo

PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" agent \
  --workspace-id smoke-agent \
  "补充一下，这是一个 ToB 的 HIS 产品，主要通过网页端使用，诊所前台提出来的，前台自己在操作，店长对结果负责。"
echo

PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" agent \
  --workspace-id smoke-agent \
  "现在主要靠前台手工翻列表提醒，研发资源比较紧张，我更倾向先看看流程约束能不能解决。"
echo

echo "== 平台工具：工作区概览 =="
PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "$TMP_DIR" tool --format json \
  --tool-name platform-workspace-overview \
  --payload-json '{"workspace_id":"smoke-agent"}'
echo

echo "== 人类风格用例测试 =="
PYTHONPATH=src python3 -m unittest tests.test_human_like_flows
echo

echo "== 全量测试 =="
PYTHONPATH=src python3 -m unittest discover -s tests
echo

echo "== PM Method Agent 手动冒烟完成 =="
