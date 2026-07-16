const STATUS_LABELS = {
  pending: "待审核",
  approved: "已批准",
  rejected: "已拒绝",
  published: "已发布",
};

const DESC_CHAR_LIMIT = 1000; // XHS note body hard limit

async function api(path, options) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || data.message || `请求失败 (${resp.status})`);
  }
  return data;
}

/* ---------- Accounts ---------- */

function accountRow(which) {
  return document.querySelector(`.account-row[data-which="${which}"]`);
}

function setAccountBadge(which, cls, text) {
  const badge = accountRow(which).querySelector('[data-role="status"]');
  badge.className = `badge ${cls}`;
  badge.textContent = text;
}

async function loadAccounts() {
  const data = await api("/api/accounts");
  for (const which of ["pc", "creator"]) {
    const info = data[which];
    const metaEl = accountRow(which).querySelector('[data-role="updated"]');
    if (info.configured) {
      const d = new Date(info.updated_at * 1000);
      metaEl.textContent = `上次更新: ${d.toLocaleString()}`;
    } else {
      metaEl.textContent = "未配置";
    }
  }
}

async function testAccount(which) {
  setAccountBadge(which, "", "测试中...");
  try {
    const result = await api("/api/accounts/test", {
      method: "POST",
      body: JSON.stringify({ which }),
    });
    setAccountBadge(which, result.ok ? "ok" : "fail", result.ok ? "正常" : "已失效");
    return result;
  } catch (err) {
    setAccountBadge(which, "fail", "检测出错");
    return { ok: false, message: err.message };
  }
}

async function testAllAccountsAndWarn() {
  const [pcResult, creatorResult] = await Promise.all([
    testAccount("pc"),
    testAccount("creator"),
  ]);
  const failed = [];
  if (!pcResult.ok) failed.push("pc");
  if (!creatorResult.ok) failed.push("creator");

  const banner = document.getElementById("banner");
  if (failed.length) {
    banner.textContent = `⚠️ ${failed.join(" / ")} cookie 可能已失效,请在下方账号面板更新`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

document.querySelectorAll(".account-row").forEach((row) => {
  const which = row.dataset.which;
  row.querySelector('[data-action="test"]').addEventListener("click", () => testAccount(which));
  row.querySelector('[data-action="save"]').addEventListener("click", async () => {
    const cookieStr = row.querySelector('[data-role="cookie-input"]').value.trim();
    if (!cookieStr) return;
    try {
      await api("/api/accounts", {
        method: "POST",
        body: JSON.stringify({ [which]: cookieStr }),
      });
      row.querySelector('[data-role="cookie-input"]').value = "";
      await loadAccounts();
      await testAccount(which);
    } catch (err) {
      alert(`保存失败: ${err.message}`);
    }
  });
});

/* ---------- Explore / Draft ---------- */

document.getElementById("explore-run").addEventListener("click", async () => {
  const theme = document.getElementById("explore-theme").value.trim();
  if (!theme) return;
  const btn = document.getElementById("explore-run");
  const log = document.getElementById("explore-log");
  btn.disabled = true;
  btn.textContent = "运行中...";
  log.textContent = "正在拆解话题、采集笔记...";
  try {
    const result = await api("/api/explore", {
      method: "POST",
      body: JSON.stringify({
        theme,
        topics: Number(document.getElementById("explore-topics").value),
        limit: Number(document.getElementById("explore-limit").value),
      }),
    });
    log.textContent = JSON.stringify(result, null, 2);
    await loadTree();
  } catch (err) {
    log.textContent = `失败: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "开始 Explore";
  }
});

document.getElementById("draft-run").addEventListener("click", async () => {
  const btn = document.getElementById("draft-run");
  const log = document.getElementById("explore-log");
  btn.disabled = true;
  btn.textContent = "运行中...";
  log.textContent = "正在综合生成草稿...";
  try {
    const result = await api("/api/draft", { method: "POST" });
    log.textContent = JSON.stringify(result, null, 2);
    await Promise.all([loadTree(), loadDrafts(), loadApprovedCount()]);
  } catch (err) {
    log.textContent = `失败: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "对新采集的笔记生成草稿";
  }
});

/* ---------- Tree ---------- */

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}

function renderTree(explorations) {
  const root = document.getElementById("tree-root");
  if (!explorations.length) {
    root.innerHTML = '<p class="meta">还没有数据,先跑一次 Explore。</p>';
    return;
  }

  root.innerHTML = explorations
    .map((exp) => {
      const subtopicsHtml = exp.subtopics
        .map((sub) => {
          const notesHtml = sub.notes
            .map(
              (n) =>
                `<li><a href="${escapeHtml(n.url)}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a></li>`
            )
            .join("");
          const draftsHtml = sub.drafts
            .map(
              (d) =>
                `<li><span class="tree-draft-link" data-draft-id="${d.id}">${escapeHtml(d.new_title)}</span> <span class="badge ${d.status}">${STATUS_LABELS[d.status] || d.status}</span></li>`
            )
            .join("");
          return `
            <li class="tree-subtopic">
              <div class="tree-subtopic-title">${escapeHtml(sub.keyword)}</div>
              <div class="tree-branch">
                <div class="tree-notes"><strong>采集笔记 (${sub.notes.length})</strong><ul>${notesHtml || "<li>无</li>"}</ul></div>
                <div class="tree-drafts"><strong>生成草稿</strong><ul>${draftsHtml || "<li>还没生成</li>"}</ul></div>
              </div>
            </li>`;
        })
        .join("");
      return `
        <div class="tree-exploration">
          <div class="tree-theme">${escapeHtml(exp.theme)}</div>
          <ul class="tree-subtopics">${subtopicsHtml}</ul>
        </div>`;
    })
    .join("");

  root.querySelectorAll(".tree-draft-link").forEach((el) => {
    el.addEventListener("click", () => {
      const card = document.getElementById(`draft-${el.dataset.draftId}`);
      if (card) {
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        card.classList.add("highlight");
        setTimeout(() => card.classList.remove("highlight"), 1500);
      }
    });
  });
}

async function loadTree() {
  const data = await api("/api/tree");
  renderTree(data.tree);
}

/* ---------- Draft review ---------- */

function draftCard(draft) {
  const thumbs = draft.image_paths
    .map((p) => `<img src="/images/${escapeHtml(p.split("/data/drafts/")[1] || "")}" />`)
    .join("");
  return `
    <div class="draft-card" id="draft-${draft.id}">
      <div class="draft-card-head">
        <strong>#${draft.id} ${escapeHtml(draft.topic)}</strong>
        <span class="meta">来源: ${draft.source_titles.map(escapeHtml).join(" | ")}</span>
      </div>
      <label>标题</label>
      <input type="text" class="title" value="${escapeHtml(draft.new_title)}" />
      <label>正文</label>
      <textarea class="desc">${escapeHtml(draft.new_desc)}</textarea>
      <p class="char-count"></p>
      ${draft.image_paths.length ? `<div class="draft-thumbs">${thumbs}</div>` : '<p class="meta">(无配图,需要你自己补充)</p>'}
      <div class="draft-actions">
        <button class="approve">批准</button>
        <button class="reject">拒绝</button>
        <button class="save">保存修改</button>
      </div>
    </div>`;
}

async function loadDrafts() {
  const data = await api("/api/drafts?status=pending");
  const container = document.getElementById("draft-list");
  if (!data.drafts.length) {
    container.innerHTML = '<p class="meta">没有待审核的草稿。</p>';
    return;
  }
  container.innerHTML = data.drafts.map(draftCard).join("");

  data.drafts.forEach((draft) => {
    const card = document.getElementById(`draft-${draft.id}`);

    const descEl = card.querySelector(".desc");
    const counterEl = card.querySelector(".char-count");
    const updateCounter = () => {
      const len = descEl.value.length;
      counterEl.textContent = `${len} / ${DESC_CHAR_LIMIT} 字`;
      counterEl.classList.toggle("over-limit", len > DESC_CHAR_LIMIT);
    };
    descEl.addEventListener("input", updateCounter);
    updateCounter();

    card.querySelector(".approve").addEventListener("click", async () => {
      try {
        await api(`/api/drafts/${draft.id}/approve`, { method: "POST" });
        await Promise.all([loadDrafts(), loadTree(), loadApprovedCount()]);
      } catch (err) {
        alert(`操作失败: ${err.message}`);
      }
    });
    card.querySelector(".reject").addEventListener("click", async () => {
      try {
        await api(`/api/drafts/${draft.id}/reject`, { method: "POST" });
        await Promise.all([loadDrafts(), loadTree()]);
      } catch (err) {
        alert(`操作失败: ${err.message}`);
      }
    });
    card.querySelector(".save").addEventListener("click", async () => {
      const newTitle = card.querySelector(".title").value;
      const newDesc = card.querySelector(".desc").value;
      try {
        await api(`/api/drafts/${draft.id}/update`, {
          method: "POST",
          body: JSON.stringify({ new_title: newTitle, new_desc: newDesc }),
        });
        await loadTree();
      } catch (err) {
        alert(`保存失败: ${err.message}`);
      }
    });
  });
}

/* ---------- Publish ---------- */

async function loadApprovedCount() {
  const data = await api("/api/drafts?status=approved");
  document.getElementById("approved-count").textContent = data.drafts.length;
  document.getElementById("real-publish-btn").disabled =
    !document.getElementById("confirm-real-publish").checked || data.drafts.length === 0;
}

document.getElementById("confirm-real-publish").addEventListener("change", loadApprovedCount);

document.getElementById("dry-run-btn").addEventListener("click", async () => {
  const log = document.getElementById("publish-log");
  log.textContent = "运行中...";
  try {
    const result = await api("/api/publish", {
      method: "POST",
      body: JSON.stringify({ dry_run: true }),
    });
    log.textContent = JSON.stringify(result, null, 2);
  } catch (err) {
    log.textContent = `失败: ${err.message}`;
  }
});

document.getElementById("real-publish-btn").addEventListener("click", async () => {
  const countEl = document.getElementById("approved-count");
  const count = Number(countEl.textContent);
  if (!confirm(`确定要真实发布 ${count} 条草稿吗?这是公开、不可逆的操作。`)) return;

  const log = document.getElementById("publish-log");
  log.textContent = "发布中...";
  try {
    const result = await api("/api/publish", {
      method: "POST",
      body: JSON.stringify({ dry_run: false }),
    });
    log.textContent = JSON.stringify(result, null, 2);
    await Promise.all([loadDrafts(), loadTree(), loadApprovedCount()]);
  } catch (err) {
    log.textContent = `失败: ${err.message}`;
  }
});

/* ---------- Init ---------- */

(async function init() {
  await loadAccounts();
  await testAllAccountsAndWarn();
  await Promise.all([loadTree(), loadDrafts(), loadApprovedCount()]);
})();
