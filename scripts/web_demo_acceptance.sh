#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORE_DIR="${TMPDIR:-/tmp}/pmma-web-acceptance"
PORT="${PMMA_WEB_ACCEPT_PORT:-}"
URL="http://127.0.0.1:${PORT}/"
SERVER_PID=""
OPEN_PID=""

cleanup() {
  if [[ -n "${OPEN_PID}" ]] && kill -0 "${OPEN_PID}" >/dev/null 2>&1; then
    kill "${OPEN_PID}" >/dev/null 2>&1 || true
    wait "${OPEN_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  playwright-cli close >/dev/null 2>&1 || true
}

trap cleanup EXIT

assert_eq() {
  local actual="$1"
  local expected="$2"
  local message="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    printf '验收失败：%s\n' "${message}" >&2
    printf '  预期：%s\n' "${expected}" >&2
    printf '  实际：%s\n' "${actual}" >&2
    exit 1
  fi
}

assert_contains() {
  local actual="$1"
  local expected="$2"
  local message="$3"
  if [[ "${actual}" != *"${expected}"* ]]; then
    printf '验收失败：%s\n' "${message}" >&2
    printf '  预期包含：%s\n' "${expected}" >&2
    printf '  实际：%s\n' "${actual}" >&2
    exit 1
  fi
}

wait_for_snapshot_contains() {
  local expected_fragment="$1"
  local snapshot=""
  for _ in {1..60}; do
    snapshot="$(playwright-cli snapshot 2>/dev/null || true)"
    if [[ "${snapshot}" == *"${expected_fragment}"* ]]; then
      printf '%s' "${snapshot}"
      return 0
    fi
    sleep 1
  done
  printf '验收失败：页面快照在预期时间内没有稳定下来\n' >&2
  printf '  预期包含：%s\n' "${expected_fragment}" >&2
  printf '  实际：%s\n' "${snapshot}" >&2
  exit 1
}

if [[ -z "${PORT}" ]]; then
  PORT="$(python3 - <<'PY'
import socket

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
)"
fi

URL="http://127.0.0.1:${PORT}/"

printf '启动本地网页 demo 服务：%s\n' "${URL}"
rm -rf "${STORE_DIR}"
mkdir -p "${STORE_DIR}"

(
  cd "${ROOT_DIR}"
  PYTHONPATH=src python3 -m pm_method_agent.cli --store-dir "${STORE_DIR}" serve --port "${PORT}"
) >/tmp/pmma-web-acceptance.log 2>&1 &
SERVER_PID=$!

for _ in {1..30}; do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null; then
    break
  fi
  if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    printf '验收失败：本地服务在健康检查通过前提前退出\n' >&2
    tail -n 40 /tmp/pmma-web-acceptance.log >&2 || true
    exit 1
  fi
  sleep 1
done

if ! curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null; then
  printf '验收失败：本地服务没有在预期时间内通过健康检查\n' >&2
  tail -n 40 /tmp/pmma-web-acceptance.log >&2 || true
  exit 1
fi

playwright-cli open "${URL}" >/dev/null 2>&1 &
OPEN_PID=$!
sleep 2

console_summary="$(playwright-cli console)"
assert_contains "${console_summary}" "Total messages: 0" "首屏不应出现控制台报错"

playwright-cli fill "#composerInput" "最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。" >/dev/null
playwright-cli click "#sendMessageButton" >/dev/null
first_snapshot="$(wait_for_snapshot_contains "已按新的输入创建分析案例")"

first_case_id="$(printf '%s\n' "${first_snapshot}" | grep -oE 'case-[0-9a-f]{8}' | head -n 1)"
assert_contains "${first_snapshot}" "已按新的输入创建分析案例" "第一轮应创建新案例"

playwright-cli fill "#composerInput" "这是一个 ToB 的 HIS 产品，主要通过网页端使用，前台在操作，店长会看结果。" >/dev/null
playwright-cli click "#sendMessageButton" >/dev/null
second_snapshot="$(wait_for_snapshot_contains "已承接当前活跃案例并继续推进")"

assert_contains "${second_snapshot}" "验证设计" "第二轮补充后应继续推进阶段"
assert_contains "${second_snapshot}" "已累计 2 轮输入" "历史摘要应反映两轮输入"

playwright-cli fill "#composerInput" "还有一个问题，新用户注册后发帖率也偏低，想一起看看。" >/dev/null
playwright-cli click "#sendMessageButton" >/dev/null
third_snapshot="$(wait_for_snapshot_contains "已按新的输入创建分析案例")"

recent_count="$(printf '%s\n' "${third_snapshot}" | grep -o 'generic \[ref=.*\]: "2"' | head -n 1 || true)"
second_case_id="$(printf '%s\n' "${third_snapshot}" | grep -oE 'case-[0-9a-f]{8}' | head -n 1)"
assert_contains "${third_snapshot}" "\"2\"" "新增第二个案例后，最近案例数量应为 2"

playwright-cli click "getByRole('button', { name: /${first_case_id}/ })" >/dev/null
switch_snapshot="$(wait_for_snapshot_contains "已切换到当前案例")"
switch_case_occurrences="$(printf '%s\n' "${switch_snapshot}" | grep -o "${first_case_id}" | wc -l | tr -d ' ')"

assert_contains "${switch_snapshot}" "当前案例：${first_case_id}" "切换案例后，左侧工作区当前案例应同步"
if (( switch_case_occurrences < 3 )); then
  printf '验收失败：切换案例后，目标案例没有稳定出现在当前快照里\n' >&2
  printf '  目标案例：%s\n' "${first_case_id}" >&2
  printf '  出现次数：%s\n' "${switch_case_occurrences}" >&2
  exit 1
fi

printf '\n网页 demo 验收通过。\n'
printf '  第一条案例：%s\n' "${first_case_id}"
printf '  第二条案例：%s\n' "${second_case_id}"
printf '  验收地址：%s\n' "${URL}"
