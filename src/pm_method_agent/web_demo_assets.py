from __future__ import annotations

from typing import Optional, Tuple


WEB_DEMO_HTML = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PM Method Agent</title>
    <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml" />
    <link rel="stylesheet" href="/assets/web-demo.css" />
  </head>
  <body>
    <div class="page-shell">
      <aside class="sidebar">
        <div class="brand-block">
          <p class="eyebrow">PM Method Agent</p>
          <h1>问题定义，不从长文档开始。</h1>
          <p class="lede">
            这里不是通用聊天页。它更像一个轻量工作台，用来承接需求草稿、继续补充和阶段推进。
          </p>
        </div>

        <section class="panel workspace-panel">
          <div class="panel-heading">
            <h2>工作区</h2>
            <button id="refreshWorkspaceButton" class="ghost-button" type="button">刷新</button>
          </div>
          <label class="field-label" for="workspaceIdInput">工作区标识</label>
          <div class="workspace-input-row">
            <input id="workspaceIdInput" type="text" spellcheck="false" value="demo" />
            <button id="loadWorkspaceButton" type="button">载入</button>
          </div>
          <div id="workspaceMeta" class="workspace-meta"></div>
        </section>

        <section class="panel recent-panel">
          <div class="panel-heading">
            <h2>最近案例</h2>
            <span id="recentCountBadge" class="count-badge">0</span>
          </div>
          <div id="recentCases" class="recent-list empty-list">
            <p>当前工作区还没有案例。</p>
          </div>
        </section>
      </aside>

      <main class="main-stage">
        <header class="hero">
          <div>
            <p class="eyebrow">主交互区</p>
            <h2 id="heroTitle">先给一句真实草稿。</h2>
          </div>
          <div id="statusPills" class="status-pills"></div>
        </header>

        <section class="panel composer-panel">
          <div class="composer-header">
            <div>
              <h3>开始或继续</h3>
              <p id="systemMessage" class="muted">
                直接输入一个想法、抱怨、指标异常或带方案倾向的需求描述都可以。
              </p>
              <div id="composerMeta" class="composer-meta"></div>
            </div>
            <button id="clearComposerButton" class="ghost-button" type="button">清空</button>
          </div>
          <div class="example-row">
            <button class="example-chip" type="button" data-example="最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。">
              诊所提醒漏发
            </button>
            <button class="example-chip" type="button" data-example="最近淘宝售后相关反馈不少，但我还没想清楚，这次到底是想提升退货发起率，还是降低售后投诉率。">
              售后目标没收住
            </button>
            <button class="example-chip" type="button" data-example="想增加一个新手引导浮层，提升新用户发帖率。">
              带方案的增长草稿
            </button>
          </div>
          <textarea
            id="composerInput"
            placeholder="例如：最近诊所前台经常漏掉复诊患者的就诊前提醒，我在想这件事是不是该处理。"
          ></textarea>
          <div class="composer-actions">
            <button id="sendMessageButton" class="primary-button" type="button">发送</button>
            <p class="hint">同一个工作区会自动承接当前活跃案例。</p>
          </div>
        </section>

        <section class="panel card-panel">
          <div class="panel-heading">
            <h2>当前卡片</h2>
            <span id="activeCaseBadge" class="case-badge">未加载</span>
          </div>
          <div id="cardMeta" class="card-meta"></div>
          <p class="section-kicker">快速导航</p>
          <div id="cardOutline" class="card-outline empty-list">
            <p>卡片展开后，这里会列出重点章节。</p>
          </div>
          <p class="section-kicker">本轮摘要</p>
          <div id="cardDigest" class="card-digest empty-list">
            <p>当前阶段最值得先看的内容，会先收在这里。</p>
          </div>
          <p class="section-kicker">主卡正文</p>
          <div id="cardContent" class="render-surface empty-surface">
            <p>这里会显示当前案例的主卡片。</p>
          </div>
        </section>
      </main>

      <aside class="detail-rail">
        <div class="detail-tabs" role="tablist" aria-label="辅助信息">
          <button class="detail-tab is-active" type="button" data-tab="history">历史</button>
          <button class="detail-tab" type="button" data-tab="approvals">审批</button>
        </div>

        <section id="historyPanel" class="panel detail-panel">
          <div class="panel-heading">
            <h2>案例历史</h2>
            <button id="refreshHistoryButton" class="ghost-button" type="button">刷新</button>
          </div>
          <p class="section-kicker">关键动作</p>
          <div id="historyTimeline" class="history-timeline empty-list">
            <p>选中案例后，会先把关键动作按顺序收起来。</p>
          </div>
          <p class="section-kicker">过程概览</p>
          <div id="historyDigest" class="history-digest empty-list">
            <p>这里会先概览这段过程推进到了哪里。</p>
          </div>
          <p class="section-kicker">完整记录</p>
          <div id="historyContent" class="render-surface empty-surface">
            <p>选中案例后，这里会显示历史记录。</p>
          </div>
        </section>

        <section id="approvalsPanel" class="panel detail-panel is-hidden">
          <div class="panel-heading">
            <h2>待处理审批</h2>
            <button id="refreshApprovalsButton" class="ghost-button" type="button">刷新</button>
          </div>
          <div id="approvalsContent" class="approvals-list empty-list">
            <p>当前没有待确认操作。</p>
          </div>
        </section>
      </aside>
    </div>

    <div id="toast" class="toast" aria-live="polite"></div>
    <script src="/assets/web-demo.js"></script>
  </body>
</html>
"""


WEB_DEMO_CSS = """\
:root {
  --bg: #f3efe6;
  --panel: rgba(255, 252, 245, 0.82);
  --panel-strong: rgba(255, 250, 240, 0.94);
  --line: rgba(61, 52, 41, 0.12);
  --line-strong: rgba(61, 52, 41, 0.22);
  --text: #241f1a;
  --muted: #6c6255;
  --accent: #b34d2f;
  --accent-soft: rgba(179, 77, 47, 0.12);
  --shadow: 0 24px 60px rgba(53, 38, 20, 0.12);
  --radius-xl: 28px;
  --radius-lg: 20px;
  --radius-md: 14px;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  min-height: 100%;
  color: var(--text);
  background:
    radial-gradient(circle at top left, rgba(179, 77, 47, 0.16), transparent 28%),
    radial-gradient(circle at right 12% top 24%, rgba(92, 138, 124, 0.14), transparent 24%),
    linear-gradient(180deg, #f8f4eb 0%, #efe7d8 100%);
  font-family: "PingFang SC", "Hiragino Sans GB", "Source Han Sans SC", "Microsoft YaHei", sans-serif;
}

body::before {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(36, 31, 26, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(36, 31, 26, 0.02) 1px, transparent 1px);
  background-size: 22px 22px;
  content: "";
  opacity: 0.42;
}

button,
input,
textarea {
  font: inherit;
}

.page-shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 312px minmax(0, 1fr) 340px;
  gap: 18px;
  min-height: 100vh;
  padding: 18px;
}

.sidebar,
.main-stage,
.detail-rail {
  min-width: 0;
}

.brand-block {
  padding: 10px 4px 18px;
}

.eyebrow {
  margin: 0 0 10px;
  color: var(--accent);
  letter-spacing: 0.18em;
  font-size: 12px;
  text-transform: uppercase;
}

.brand-block h1,
.hero h2 {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
  line-height: 1.04;
  font-weight: 700;
}

.brand-block h1 {
  font-size: clamp(30px, 4vw, 42px);
}

.hero h2 {
  font-size: clamp(26px, 3vw, 38px);
}

.lede,
.muted,
.hint {
  color: var(--muted);
}

.panel {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  background: var(--panel);
  box-shadow: var(--shadow);
  backdrop-filter: blur(18px);
}

.panel::before {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.48), rgba(255, 255, 255, 0.06));
  content: "";
  pointer-events: none;
}

.panel > * {
  position: relative;
  z-index: 1;
}

.workspace-panel,
.recent-panel,
.composer-panel,
.card-panel,
.detail-panel {
  padding: 18px;
}

.card-panel,
.detail-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.main-stage {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.detail-rail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 4px 0;
}

.status-pills,
.card-meta,
.workspace-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill,
.case-badge,
.count-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
  color: var(--muted);
  font-size: 13px;
}

.pill.is-strong,
.primary-button,
.detail-tab.is-active {
  border-color: rgba(179, 77, 47, 0.24);
  background: linear-gradient(180deg, #bc5637 0%, #9f4328 100%);
  color: #fff8f3;
}

.panel-heading,
.composer-header,
.workspace-input-row,
.composer-actions,
.approval-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-heading h2,
.composer-header h3 {
  margin: 0;
  font-size: 15px;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 13px;
}

.section-kicker {
  margin: 2px 0 -2px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.workspace-input-row {
  margin-top: 10px;
}

input,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.68);
  color: var(--text);
  outline: none;
  transition: border-color 140ms ease, transform 140ms ease, box-shadow 140ms ease;
}

input {
  min-height: 44px;
  padding: 0 14px;
}

textarea {
  min-height: 144px;
  resize: vertical;
  padding: 14px 16px;
  line-height: 1.7;
}

input:focus,
textarea:focus {
  border-color: rgba(179, 77, 47, 0.5);
  box-shadow: 0 0 0 4px rgba(179, 77, 47, 0.12);
}

button {
  cursor: pointer;
  border: 0;
  border-radius: 999px;
  padding: 0 16px;
  min-height: 42px;
  transition: transform 140ms ease, box-shadow 140ms ease, opacity 140ms ease;
}

button:hover {
  transform: translateY(-1px);
}

button:disabled {
  cursor: progress;
  opacity: 0.68;
  transform: none;
}

.primary-button {
  min-width: 92px;
  box-shadow: 0 16px 28px rgba(159, 67, 40, 0.24);
}

.ghost-button,
.example-chip,
.recent-case {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.55);
  color: var(--text);
}

.ghost-button {
  min-height: 34px;
  padding: 0 12px;
}

.composer-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.soft-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(61, 52, 41, 0.1);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.48);
  color: var(--muted);
  font-size: 12px;
}

.soft-pill.is-accent {
  border-color: rgba(179, 77, 47, 0.18);
  background: rgba(255, 244, 238, 0.72);
  color: #8f442e;
}

.example-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0 12px;
}

.example-chip {
  min-height: 34px;
  padding: 0 12px;
  font-size: 13px;
}

.recent-list,
.approvals-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.recent-case {
  width: 100%;
  display: grid;
  gap: 8px;
  border-radius: 18px;
  padding: 14px;
  text-align: left;
}

.recent-case.is-active {
  border-color: rgba(179, 77, 47, 0.36);
  background: linear-gradient(180deg, rgba(179, 77, 47, 0.16), rgba(255, 255, 255, 0.72));
}

.recent-case-meta,
.recent-case-footer,
.recent-case-summary,
.approval-reason {
  display: block;
}

.recent-case-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
}

.recent-case-stage {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(36, 31, 26, 0.06);
}

.recent-case-state {
  color: var(--muted);
}

.recent-case-flag {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(179, 77, 47, 0.12);
  color: var(--accent);
}

.recent-case-title {
  display: block;
  margin: 0;
  font-weight: 700;
  line-height: 1.55;
}

.recent-case-footer {
  color: var(--muted);
  font-size: 12px;
}

.recent-case-summary,
.recent-case-footer {
  color: var(--muted);
  line-height: 1.6;
  font-size: 13px;
}

.render-surface {
  border: 1px solid rgba(61, 52, 41, 0.08);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(250, 246, 239, 0.9));
  padding: 18px 18px 20px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.52);
  line-height: 1.8;
}

.card-outline,
.history-timeline,
.card-digest,
.history-digest {
  display: grid;
  gap: 10px;
  margin: 16px 0 18px;
}

.card-outline {
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.outline-chip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 52px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.64);
  color: var(--text);
  padding: 10px 12px;
  text-align: left;
}

.outline-chip:hover {
  border-color: rgba(179, 77, 47, 0.26);
  background: rgba(255, 248, 243, 0.84);
  box-shadow: 0 12px 20px rgba(61, 52, 41, 0.08);
}

.outline-chip-index {
  color: var(--accent);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.outline-chip-text {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 1.45;
}

.digest-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(248, 240, 227, 0.86));
  padding: 14px 15px;
}

.digest-card.is-warm {
  border-color: rgba(179, 77, 47, 0.22);
  background: linear-gradient(180deg, rgba(255, 244, 238, 0.94), rgba(249, 235, 225, 0.88));
}

.digest-card.is-calm {
  border-color: rgba(79, 124, 115, 0.2);
  background: linear-gradient(180deg, rgba(241, 249, 247, 0.94), rgba(235, 245, 243, 0.88));
}

.digest-label {
  display: block;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.digest-value {
  display: block;
  font-size: 15px;
  line-height: 1.65;
}

.digest-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--muted);
}

.digest-list li + li {
  margin-top: 6px;
}

.render-surface > :first-child {
  margin-top: 0;
}

.render-surface > :last-child {
  margin-bottom: 0;
}

.render-surface > * {
  max-width: 72ch;
}

.render-surface h1,
.render-surface h2,
.render-surface h3 {
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
  line-height: 1.2;
  scroll-margin-top: 18px;
}

.render-surface h1 {
  margin: 0 0 14px;
  font-size: 28px;
}

.render-surface h2 {
  margin: 34px 0 10px;
  padding-top: 18px;
  border-top: 1px solid rgba(61, 52, 41, 0.08);
  font-size: 22px;
}

.render-surface h2:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.render-surface h3 {
  margin: 22px 0 8px;
  font-size: 18px;
}

.render-surface p,
.render-surface ul,
.render-surface ol {
  margin: 0 0 12px;
}

.render-surface ul,
.render-surface ol {
  padding-left: 20px;
}

.render-surface code {
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(36, 31, 26, 0.08);
  font-family: "SFMono-Regular", "Menlo", "Monaco", monospace;
  font-size: 0.92em;
}

.render-surface blockquote {
  margin: 0 0 14px;
  padding: 13px 14px;
  border: 1px solid rgba(179, 77, 47, 0.14);
  border-radius: 16px;
  background: rgba(179, 77, 47, 0.06);
  color: var(--muted);
}

.empty-surface,
.empty-list {
  color: var(--muted);
}

.detail-tabs {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.detail-tab {
  min-height: 40px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.58);
}

.detail-panel.is-hidden {
  display: none;
}

.approval-card {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--panel-strong);
  padding: 14px;
}

.timeline-item {
  position: relative;
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 10px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  padding: 13px 14px;
}

.timeline-item::before {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: rgba(179, 77, 47, 0.22);
  box-shadow: 0 0 0 4px rgba(179, 77, 47, 0.08);
  content: "";
}

.timeline-body {
  display: grid;
  gap: 6px;
}

.timeline-item-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.timeline-kind {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(179, 77, 47, 0.1);
  color: var(--accent);
  font-size: 12px;
}

.timeline-stage {
  color: var(--muted);
  font-size: 13px;
}

.timeline-text {
  color: var(--text);
  line-height: 1.65;
}

.approval-card h3 {
  margin: 0 0 8px;
  font-size: 15px;
}

.approval-card p {
  margin: 0 0 10px;
  color: var(--muted);
  line-height: 1.6;
}

.approval-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 10px;
}

.approval-actions button {
  min-height: 34px;
  padding: 0 12px;
}

.danger-button {
  border: 1px solid rgba(138, 31, 31, 0.12);
  background: rgba(138, 31, 31, 0.08);
  color: #7b1d1d;
}

.toast {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 20;
  min-width: 220px;
  max-width: 320px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(36, 31, 26, 0.92);
  color: #fff9f4;
  box-shadow: 0 18px 34px rgba(36, 31, 26, 0.24);
  opacity: 0;
  transform: translateY(12px);
  pointer-events: none;
  transition: opacity 160ms ease, transform 160ms ease;
}

.toast.is-visible {
  opacity: 1;
  transform: translateY(0);
}

.composer-panel.is-sending {
  border-color: rgba(179, 77, 47, 0.24);
}

.composer-panel.is-sending .primary-button {
  box-shadow: 0 12px 24px rgba(159, 67, 40, 0.16);
}

.composer-panel.is-sending::after {
  position: absolute;
  right: 18px;
  top: 18px;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(180deg, #bc5637 0%, #9f4328 100%);
  box-shadow: 0 0 0 10px rgba(179, 77, 47, 0.12);
  content: "";
  animation: pulseDot 1.2s ease infinite;
  z-index: 2;
}

@keyframes pulseDot {
  0%,
  100% {
    transform: scale(0.92);
    opacity: 0.72;
  }

  50% {
    transform: scale(1.12);
    opacity: 1;
  }
}

@media (max-width: 1180px) {
  .page-shell {
    grid-template-columns: 1fr;
  }

  .hero {
    flex-direction: column;
  }

  .render-surface > * {
    max-width: none;
  }
}

@media (max-width: 720px) {
  .page-shell {
    padding: 12px;
  }

  .workspace-input-row,
  .composer-actions,
  .panel-heading,
  .composer-header {
    flex-direction: column;
    align-items: stretch;
  }

  .detail-tabs {
    position: sticky;
    top: 0;
    z-index: 4;
  }
}
"""


WEB_DEMO_JS = """\
(() => {
  const state = {
    workspaceId: "demo",
    activeCaseId: "",
    currentCase: null,
    recentCases: [],
    approvals: [],
  };

  const els = {
    workspaceIdInput: document.getElementById("workspaceIdInput"),
    loadWorkspaceButton: document.getElementById("loadWorkspaceButton"),
    refreshWorkspaceButton: document.getElementById("refreshWorkspaceButton"),
    workspaceMeta: document.getElementById("workspaceMeta"),
    recentCountBadge: document.getElementById("recentCountBadge"),
    recentCases: document.getElementById("recentCases"),
    heroTitle: document.getElementById("heroTitle"),
    statusPills: document.getElementById("statusPills"),
    systemMessage: document.getElementById("systemMessage"),
    composerMeta: document.getElementById("composerMeta"),
    composerInput: document.getElementById("composerInput"),
    sendMessageButton: document.getElementById("sendMessageButton"),
    clearComposerButton: document.getElementById("clearComposerButton"),
    composerPanel: document.querySelector(".composer-panel"),
    activeCaseBadge: document.getElementById("activeCaseBadge"),
    cardMeta: document.getElementById("cardMeta"),
    cardOutline: document.getElementById("cardOutline"),
    cardDigest: document.getElementById("cardDigest"),
    cardContent: document.getElementById("cardContent"),
    historyTimeline: document.getElementById("historyTimeline"),
    historyDigest: document.getElementById("historyDigest"),
    historyContent: document.getElementById("historyContent"),
    approvalsContent: document.getElementById("approvalsContent"),
    refreshHistoryButton: document.getElementById("refreshHistoryButton"),
    refreshApprovalsButton: document.getElementById("refreshApprovalsButton"),
    toast: document.getElementById("toast"),
    historyPanel: document.getElementById("historyPanel"),
    approvalsPanel: document.getElementById("approvalsPanel"),
  };

  function stageLabel(value) {
    const labels = {
      intake: "输入接收",
      "pre-framing": "前置收敛",
      "context-alignment": "场景对齐",
      "problem-definition": "问题定义",
      "decision-challenge": "决策挑战",
      "validation-design": "验证设计",
      blocked: "已阻塞",
      done: "已完成",
      deferred: "已暂缓",
      completed: "已完成",
      idle: "空闲",
    };
    return labels[value] || value || "未命名";
  }

  function outputKindLabel(value) {
    const labels = {
      "review-card": "审查卡",
      "context-question-card": "场景补充卡",
      "stage-block-card": "阶段阻塞卡",
      "decision-gate-card": "决策关口卡",
      "continue-guidance-card": "继续卡",
    };
    return labels[value] || value || "卡片";
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function inlineFormat(value) {
    return escapeHtml(value).replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function shortText(value, limit = 88) {
    const normalized = String(value || "").replace(/\\s+/g, " ").trim();
    if (!normalized) {
      return "";
    }
    if (normalized.length <= limit) {
      return normalized;
    }
    return `${normalized.slice(0, limit - 1)}…`;
  }

  function buildMarkdownSections(text, sectionPrefix = "section") {
    const source = String(text || "").trim();
    if (!source) {
      return {
        html: "<p>暂无内容。</p>",
        headings: [],
      };
    }

    const lines = source.split(/\\r?\\n/);
    const parts = [];
    let listType = "";
    let headingIndex = 0;
    const headings = [];

    function closeList() {
      if (listType) {
        parts.push(listType === "ol" ? "</ol>" : "</ul>");
        listType = "";
      }
    }

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        closeList();
        return;
      }

      const headingMatch = trimmed.match(/^(#{1,3})\\s+(.*)$/);
      if (headingMatch) {
        closeList();
        const level = Math.min(headingMatch[1].length, 3);
        headingIndex += 1;
        const headingId = `${sectionPrefix}-heading-${headingIndex}`;
        const headingText = headingMatch[2];
        headings.push({
          id: headingId,
          level,
          text: headingText,
        });
        parts.push(`<h${level} id="${headingId}">${inlineFormat(headingText)}</h${level}>`);
        return;
      }

      const bulletMatch = trimmed.match(/^[-*]\\s+(.*)$/);
      if (bulletMatch) {
        if (listType !== "ul") {
          closeList();
          listType = "ul";
          parts.push("<ul>");
        }
        parts.push(`<li>${inlineFormat(bulletMatch[1])}</li>`);
        return;
      }

      const orderMatch = trimmed.match(/^\\d+\\.\\s+(.*)$/);
      if (orderMatch) {
        if (listType !== "ol") {
          closeList();
          listType = "ol";
          parts.push("<ol>");
        }
        parts.push(`<li>${inlineFormat(orderMatch[1])}</li>`);
        return;
      }

      closeList();
      parts.push(`<p>${inlineFormat(trimmed)}</p>`);
    });

    closeList();
    return {
      html: parts.join(""),
      headings,
    };
  }

  function renderMarkdownish(text, sectionPrefix = "section") {
    return buildMarkdownSections(text, sectionPrefix).html;
  }

  function renderCardOutline(headings) {
    if (!headings || !headings.length) {
      els.cardOutline.className = "card-outline empty-list";
      els.cardOutline.innerHTML = "<p>卡片展开后，这里会列出重点章节。</p>";
      return;
    }

    const visibleHeadings = headings.filter((item) => item.level >= 2).slice(0, 6);
    if (!visibleHeadings.length) {
      els.cardOutline.className = "card-outline empty-list";
      els.cardOutline.innerHTML = "<p>这张卡片当前还没有可快速跳转的章节。</p>";
      return;
    }

    els.cardOutline.className = "card-outline";
    els.cardOutline.innerHTML = visibleHeadings
      .map(
        (item, index) => `
          <button class="outline-chip" type="button" data-scroll-target="${escapeHtml(item.id)}">
            <span class="outline-chip-index">章节 ${index + 1}</span>
            <span class="outline-chip-text">${inlineFormat(shortText(item.text, 22))}</span>
          </button>
        `
      )
      .join("");

    els.cardOutline.querySelectorAll("[data-scroll-target]").forEach((button) => {
      button.addEventListener("click", () => {
        const targetId = button.getAttribute("data-scroll-target");
        const target = targetId ? document.getElementById(targetId) : null;
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  }

  function setLoading(button, loading) {
    if (!button) {
      return;
    }
    button.disabled = loading;
  }

  async function request(path, options = {}) {
    const response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "请求失败");
    }
    return payload;
  }

  function showToast(message, isError = false) {
    els.toast.textContent = message;
    els.toast.classList.add("is-visible");
    els.toast.style.background = isError ? "rgba(107, 24, 24, 0.94)" : "rgba(36, 31, 26, 0.92)";
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      els.toast.classList.remove("is-visible");
    }, 2200);
  }

  function readWorkspaceIdFromUrl() {
    const url = new URL(window.location.href);
    return (url.searchParams.get("workspace") || "demo").trim() || "demo";
  }

  function writeWorkspaceIdToUrl(workspaceId) {
    const url = new URL(window.location.href);
    url.searchParams.set("workspace", workspaceId);
    window.history.replaceState({}, "", url.toString());
  }

  function renderWorkspaceMeta(workspace) {
    const pills = [];
    pills.push(`<span class="pill">工作区：${inlineFormat(workspace.workspace_id || state.workspaceId)}</span>`);
    pills.push(
      `<span class="pill">当前案例：${inlineFormat(workspace.active_case_id || "未设置")}</span>`
    );
    if (workspace.active_project_profile_id) {
      pills.push(`<span class="pill">项目背景：${inlineFormat(workspace.active_project_profile_id)}</span>`);
    }
    els.workspaceMeta.innerHTML = pills.join("");
  }

  function renderComposerMeta({ sending = false } = {}) {
    const items = [];
    items.push(`<span class="soft-pill">工作区：${inlineFormat(state.workspaceId || "demo")}</span>`);

    if (state.activeCaseId) {
      items.push(`<span class="soft-pill is-accent">继续当前案例：${inlineFormat(state.activeCaseId)}</span>`);
    } else {
      items.push(`<span class="soft-pill is-accent">当前会新建案例</span>`);
    }

    if (state.currentCase && state.currentCase.stage) {
      items.push(`<span class="soft-pill">当前阶段：${inlineFormat(stageLabel(state.currentCase.stage))}</span>`);
    }

    if (sending) {
      items.push(`<span class="soft-pill is-accent">正在承接这一轮输入</span>`);
    }

    els.composerMeta.innerHTML = items.join("");
  }

  function renderCardDigest(casePayload) {
    if (!casePayload) {
      els.cardDigest.className = "card-digest empty-list";
      els.cardDigest.innerHTML = "<p>当前阶段最值得先看的内容，会先收在这里。</p>";
      return;
    }

    const topFinding = (casePayload.findings || [])[0];
    const topGate = (casePayload.decision_gates || [])[0];
    const nextActions = (casePayload.next_actions || []).slice(0, 3);
    const summary = shortText(
      casePayload.normalized_summary || casePayload.blocking_reason || casePayload.raw_input,
      96
    );

    const cards = [];
    cards.push(`
      <article class="digest-card is-warm">
        <span class="digest-label">这轮重点</span>
        <span class="digest-value">${inlineFormat(summary || "先看主卡片正文。")}</span>
      </article>
    `);

    if (topFinding) {
      cards.push(`
        <article class="digest-card">
          <span class="digest-label">最先该盯的一点</span>
          <span class="digest-value">${inlineFormat(shortText(topFinding.claim || "", 88))}</span>
        </article>
      `);
    }

    if (nextActions.length) {
      cards.push(`
        <article class="digest-card is-calm">
          <span class="digest-label">建议先补</span>
          <ul class="digest-list">
            ${nextActions.map((item) => `<li>${inlineFormat(shortText(item, 52))}</li>`).join("")}
          </ul>
        </article>
      `);
    } else if (topGate) {
      cards.push(`
        <article class="digest-card is-calm">
          <span class="digest-label">当前关口</span>
          <span class="digest-value">${inlineFormat(shortText(topGate.question || "", 88))}</span>
        </article>
      `);
    }

    els.cardDigest.className = "card-digest";
    els.cardDigest.innerHTML = cards.join("");
  }

  function renderHistoryDigest(historyPayload) {
    if (!historyPayload) {
      els.historyDigest.className = "history-digest empty-list";
      els.historyDigest.innerHTML = "<p>这里会先概览这段过程推进到了哪里。</p>";
      return;
    }

    const conversationTurns = historyPayload.conversation_turns || [];
    const stageHistory = historyPayload.stage_history || [];
    const answeredQuestions = historyPayload.answered_questions || [];
    const latestTurn = conversationTurns[conversationTurns.length - 1];
    const latestText = latestTurn
      ? `${latestTurn.kind || "turn"}：${latestTurn.text || latestTurn.content || ""}`
      : "当前还没有更多历史。";

    els.historyDigest.className = "history-digest";
    els.historyDigest.innerHTML = `
      <article class="digest-card is-calm">
        <span class="digest-label">这一段进展</span>
        <span class="digest-value">
          已累计 ${conversationTurns.length} 轮输入，当前停在 ${inlineFormat(stageLabel(historyPayload.stage))}。
        </span>
      </article>
      <article class="digest-card">
        <span class="digest-label">最近一轮</span>
        <span class="digest-value">${inlineFormat(shortText(latestText, 120))}</span>
      </article>
      <article class="digest-card">
        <span class="digest-label">已确认的内容</span>
        <span class="digest-value">
          已回答 ${answeredQuestions.length} 项，阶段变化 ${stageHistory.length} 次。
        </span>
      </article>
    `;
  }

  function renderHistoryTimeline(historyPayload) {
    if (!historyPayload) {
      els.historyTimeline.className = "history-timeline empty-list";
      els.historyTimeline.innerHTML = "<p>选中案例后，会先把关键动作按顺序收起来。</p>";
      return;
    }

    const conversationTurns = historyPayload.conversation_turns || [];
    const stageHistory = historyPayload.stage_history || [];
    const items = [];

    conversationTurns.slice(-4).forEach((turn) => {
      items.push({
        kind: turn.kind || "turn",
        stage: turn.stage || historyPayload.stage || "",
        text: turn.text || turn.content || "",
      });
    });

    stageHistory.slice(-2).forEach((item) => {
      items.push({
        kind: "stage-change",
        stage: item.to_stage || item.stage || "",
        text: `${item.from_stage || "未知阶段"} -> ${item.to_stage || "未知阶段"}`,
      });
    });

    if (!items.length) {
      els.historyTimeline.className = "history-timeline empty-list";
      els.historyTimeline.innerHTML = "<p>当前案例还没有足够多的历史动作。</p>";
      return;
    }

    els.historyTimeline.className = "history-timeline";
    els.historyTimeline.innerHTML = items
      .map(
        (item) => `
          <article class="timeline-item">
            <div class="timeline-body">
              <div class="timeline-item-head">
                <span class="timeline-kind">${inlineFormat(item.kind === "stage-change" ? "阶段变化" : "用户输入")}</span>
                <span class="timeline-stage">${inlineFormat(stageLabel(item.stage || ""))}</span>
              </div>
              <div class="timeline-text">${inlineFormat(shortText(item.text || "", 120))}</div>
            </div>
          </article>
        `
      )
      .join("");
  }

  function renderRecentCases() {
    els.recentCountBadge.textContent = String(state.recentCases.length);
    if (!state.recentCases.length) {
      els.recentCases.className = "recent-list empty-list";
      els.recentCases.innerHTML = "<p>当前工作区还没有案例。</p>";
      return;
    }

    els.recentCases.className = "recent-list";
    els.recentCases.innerHTML = state.recentCases
      .map((item) => {
        const activeClass = item.case_id === state.activeCaseId ? " is-active" : "";
        const summary = shortText(item.summary || "暂无摘要", 56);
        const footer = shortText(item.case_id || "", 24);
        return `
          <button class="recent-case${activeClass}" type="button" data-case-id="${escapeHtml(item.case_id)}">
            <span class="recent-case-meta">
              <span class="recent-case-stage">${inlineFormat(stageLabel(item.stage))}</span>
              <span class="recent-case-state">${inlineFormat(stageLabel(item.workflow_state))}</span>
              ${item.case_id === state.activeCaseId ? '<span class="recent-case-flag">当前</span>' : ""}
            </span>
            <span class="recent-case-title">${inlineFormat(summary)}</span>
            <span class="recent-case-footer">案例编号：${inlineFormat(footer)}</span>
          </button>
        `;
      })
      .join("");

    els.recentCases.querySelectorAll("[data-case-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        const caseId = button.getAttribute("data-case-id");
        if (caseId) {
          await switchCase(caseId);
        }
      });
    });
  }

  function renderCaseMeta(casePayload) {
    if (!casePayload) {
      els.cardMeta.innerHTML = "";
      return;
    }

    const pills = [
      `<span class="pill is-strong">${inlineFormat(stageLabel(casePayload.stage))}</span>`,
      `<span class="pill">${inlineFormat(stageLabel(casePayload.workflow_state))}</span>`,
      `<span class="pill">${inlineFormat(outputKindLabel(casePayload.output_kind))}</span>`,
    ];
    els.cardMeta.innerHTML = pills.join("");
  }

  function renderMainResponse(response) {
    state.currentCase = response.case || null;
    state.activeCaseId = response.case ? response.case.case_id : state.activeCaseId;
    els.activeCaseBadge.textContent = state.activeCaseId || "未加载";
    els.systemMessage.textContent = response.message || "已更新当前案例。";
    els.heroTitle.textContent = state.currentCase
      ? `${stageLabel(state.currentCase.stage)}，先看这轮判断。`
      : "先给一句真实草稿。";
    renderComposerMeta();

    renderCaseMeta(response.case);
    renderCardDigest(response.case);
    const renderedCard = buildMarkdownSections(response.rendered_card || "", "card");
    renderCardOutline(renderedCard.headings);
    els.cardContent.className = "render-surface";
    els.cardContent.innerHTML = renderedCard.html;

    const statusBits = [];
    if (response.workspace && response.workspace.workspace_id) {
      statusBits.push(`<span class="pill">工作区：${inlineFormat(response.workspace.workspace_id)}</span>`);
    }
    if (response.case && response.case.mode) {
      statusBits.push(`<span class="pill">模式：${inlineFormat(response.case.mode)}</span>`);
    }
    if (response.runtime_session && response.runtime_session.turn_count != null) {
      statusBits.push(
        `<span class="pill">轮次：${inlineFormat(String(response.runtime_session.turn_count))}</span>`
      );
    }
    els.statusPills.innerHTML = statusBits.join("");
  }

  async function loadWorkspace(workspaceId, { keepComposer = false, reloadActiveCase = true } = {}) {
    state.workspaceId = workspaceId;
    writeWorkspaceIdToUrl(workspaceId);
    els.workspaceIdInput.value = workspaceId;

    const payload = await request(`/workspaces/${encodeURIComponent(workspaceId)}/cases`);
    renderWorkspaceMeta(payload.workspace);
    state.recentCases = payload.cases.recent_cases || [];
    state.activeCaseId = payload.cases.active_case_id || "";
    renderRecentCases();

    if (!keepComposer) {
      els.composerInput.value = "";
    }

    if (!state.activeCaseId) {
      state.currentCase = null;
      els.activeCaseBadge.textContent = "未加载";
      els.heroTitle.textContent = "先给一句真实草稿。";
      els.statusPills.innerHTML = "";
      els.cardMeta.innerHTML = "";
      renderComposerMeta();
      renderCardOutline([]);
      renderCardDigest(null);
      els.cardContent.className = "render-surface empty-surface";
      els.cardContent.innerHTML = "<p>这里会显示当前案例的主卡片。</p>";
      renderHistoryTimeline(null);
      renderHistoryDigest(null);
      els.historyContent.className = "render-surface empty-surface";
      els.historyContent.innerHTML = "<p>选中案例后，这里会显示历史记录。</p>";
      await loadApprovals();
      return;
    }

    if (reloadActiveCase) {
      await Promise.all([loadCase(state.activeCaseId), loadHistory(), loadApprovals()]);
      return;
    }

    await Promise.all([loadHistory(), loadApprovals()]);
  }

  async function loadCase(caseId) {
    const payload = await request(`/cases/${encodeURIComponent(caseId)}`);
    renderMainResponse({
      case: payload.case,
      rendered_card: payload.rendered_card,
      message: "已切换到当前案例。",
      workspace: { workspace_id: state.workspaceId },
      runtime_session: null,
    });
  }

  async function loadHistory() {
    if (!state.activeCaseId) {
      return;
    }
    const payload = await request(`/cases/${encodeURIComponent(state.activeCaseId)}/history`);
    renderHistoryTimeline(payload.history || null);
    renderHistoryDigest(payload.history || null);
    els.historyContent.className = "render-surface";
    els.historyContent.innerHTML = renderMarkdownish(payload.rendered_history || "");
  }

  async function loadApprovals() {
    const payload = await request(
      `/workspaces/${encodeURIComponent(state.workspaceId)}/runtime/approvals`
    );
    state.approvals = payload.pending_approvals || [];
    if (!state.approvals.length) {
      els.approvalsContent.className = "approvals-list empty-list";
      els.approvalsContent.innerHTML = "<p>当前没有待确认操作。</p>";
      return;
    }

    els.approvalsContent.className = "approvals-list";
    els.approvalsContent.innerHTML = state.approvals
      .map((item) => {
        const violation = item.violation || {};
        return `
          <article class="approval-card">
            <h3>${inlineFormat(item.tool_name || item.approval_id)}</h3>
            <p>${inlineFormat(item.action_name || "待确认动作")}</p>
            <p class="approval-reason">${inlineFormat(violation.reason || "需要人工确认后才能继续。")}</p>
            <div class="approval-actions">
              <button type="button" data-approval-action="approve" data-approval-id="${escapeHtml(
                item.approval_id
              )}">批准</button>
              <button class="ghost-button" type="button" data-approval-action="expire" data-approval-id="${escapeHtml(
                item.approval_id
              )}">过期</button>
              <button class="danger-button" type="button" data-approval-action="reject" data-approval-id="${escapeHtml(
                item.approval_id
              )}">拒绝</button>
            </div>
          </article>
        `;
      })
      .join("");

    els.approvalsContent.querySelectorAll("[data-approval-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const approvalId = button.getAttribute("data-approval-id");
        const action = button.getAttribute("data-approval-action");
        if (approvalId && action) {
          await handleApproval(action, approvalId, button);
        }
      });
    });
  }

  async function switchCase(caseId) {
    const payload = await request(`/workspaces/${encodeURIComponent(state.workspaceId)}/active-case`, {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    });
    state.activeCaseId = payload.workspace?.active_case_id || caseId;
    if (payload.workspace) {
      renderWorkspaceMeta(payload.workspace);
    }
    renderRecentCases();
    renderMainResponse({
      case: payload.case,
      rendered_card: payload.rendered_card,
      message: "已切换到当前案例。",
      workspace: payload.workspace || { workspace_id: state.workspaceId },
      runtime_session: null,
    });
    await Promise.all([loadHistory(), loadApprovals()]);
    showToast("已切换到所选案例。");
  }

  async function handleApproval(action, approvalId, button) {
    setLoading(button, true);
    try {
      await request(
        `/workspaces/${encodeURIComponent(state.workspaceId)}/runtime/approvals/${encodeURIComponent(
          approvalId
        )}/${action}`,
        {
          method: "POST",
          body: JSON.stringify({}),
        }
      );
      await loadApprovals();
      showToast(`已处理审批：${approvalId}`);
    } catch (error) {
      showToast(error.message || "审批处理失败", true);
    } finally {
      setLoading(button, false);
    }
  }

  async function sendMessage() {
    const message = els.composerInput.value.trim();
    if (!message) {
      showToast("先写一句真实输入。", true);
      els.composerInput.focus();
      return;
    }

    setLoading(els.sendMessageButton, true);
    els.composerPanel.classList.add("is-sending");
    els.sendMessageButton.textContent = "承接中";
    els.systemMessage.textContent = "正在承接这轮输入，稍等一下。";
    renderComposerMeta({ sending: true });
    try {
      const payload = await request(`/workspaces/${encodeURIComponent(state.workspaceId)}/messages`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      renderMainResponse(payload);
      if (payload.workspace) {
        renderWorkspaceMeta(payload.workspace);
      }
      await loadWorkspace(state.workspaceId, { keepComposer: true, reloadActiveCase: false });
      els.composerInput.value = "";
      showToast("已更新当前案例。");
    } catch (error) {
      showToast(error.message || "发送失败", true);
      els.systemMessage.textContent = "这一轮没有成功承接，可以再试一次。";
      renderComposerMeta();
    } finally {
      els.composerPanel.classList.remove("is-sending");
      els.sendMessageButton.textContent = "发送";
      setLoading(els.sendMessageButton, false);
    }
  }

  function bindTabs() {
    document.querySelectorAll(".detail-tab").forEach((button) => {
      button.addEventListener("click", () => {
        const target = button.getAttribute("data-tab");
        document.querySelectorAll(".detail-tab").forEach((tab) => tab.classList.remove("is-active"));
        button.classList.add("is-active");
        els.historyPanel.classList.toggle("is-hidden", target !== "history");
        els.approvalsPanel.classList.toggle("is-hidden", target !== "approvals");
      });
    });
  }

  function bindExamples() {
    document.querySelectorAll(".example-chip").forEach((button) => {
      button.addEventListener("click", () => {
        els.composerInput.value = button.getAttribute("data-example") || "";
        els.composerInput.focus();
      });
    });
  }

  function bindEvents() {
    els.loadWorkspaceButton.addEventListener("click", async () => {
      const workspaceId = els.workspaceIdInput.value.trim() || "demo";
      try {
        await loadWorkspace(workspaceId);
        showToast(`已载入工作区：${workspaceId}`);
      } catch (error) {
        showToast(error.message || "工作区载入失败", true);
      }
    });

    els.refreshWorkspaceButton.addEventListener("click", async () => {
      try {
        await loadWorkspace(state.workspaceId, { keepComposer: true });
        showToast("已刷新工作区。");
      } catch (error) {
        showToast(error.message || "刷新失败", true);
      }
    });

    els.refreshHistoryButton.addEventListener("click", async () => {
      try {
        await loadHistory();
        showToast("已刷新历史。");
      } catch (error) {
        showToast(error.message || "历史刷新失败", true);
      }
    });

    els.refreshApprovalsButton.addEventListener("click", async () => {
      try {
        await loadApprovals();
        showToast("已刷新审批。");
      } catch (error) {
        showToast(error.message || "审批刷新失败", true);
      }
    });

    els.sendMessageButton.addEventListener("click", sendMessage);
    els.clearComposerButton.addEventListener("click", () => {
      els.composerInput.value = "";
      els.composerInput.focus();
    });

    els.composerInput.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        void sendMessage();
      }
    });
  }

  async function boot() {
    bindTabs();
    bindExamples();
    bindEvents();
    state.workspaceId = readWorkspaceIdFromUrl();
    els.workspaceIdInput.value = state.workspaceId;
    renderComposerMeta();
    try {
      await loadWorkspace(state.workspaceId);
    } catch (error) {
      showToast(error.message || "页面初始化失败", true);
    }
  }

  void boot();
})();
"""


WEB_DEMO_FAVICON = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="18" fill="#f5ecdd"/>
  <path d="M19 18h18c8.3 0 15 6.7 15 15s-6.7 15-15 15H31v10h-7V18h7v23h6c4.4 0 8-3.6 8-8s-3.6-8-8-8H19z" fill="#a5472d"/>
  <circle cx="20" cy="48" r="5" fill="#4f7c73"/>
</svg>
"""


def get_web_demo_html() -> bytes:
    return WEB_DEMO_HTML.encode("utf-8")


def get_web_demo_asset(path: str) -> Optional[Tuple[str, bytes]]:
    normalized = path.strip("/")
    if normalized in {"favicon.ico", "assets/favicon.svg"}:
        return ("image/svg+xml", WEB_DEMO_FAVICON.encode("utf-8"))
    if normalized == "assets/web-demo.css":
        return ("text/css; charset=utf-8", WEB_DEMO_CSS.encode("utf-8"))
    if normalized == "assets/web-demo.js":
        return ("application/javascript; charset=utf-8", WEB_DEMO_JS.encode("utf-8"))
    return None
