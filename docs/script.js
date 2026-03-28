const KEYS_URL = "keys.json";
const FALLBACK_DOWNLOADS = {
  top15: "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker@main/top15.txt",
  full: "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker@main/good.txt",
};

function encodeKey(key) {
  return key.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function renderEntry(item) {
  return (
    '<article class="entry">' +
      '<div class="entry-rank">#' + item.rank + '</div>' +
      '<div class="entry-main">' +
        '<div class="entry-topline">' +
          '<span class="country">' + (item.flag || "🌍") + " " + item.country + "</span>" +
          '<span class="latency">' + item.latency_ms + " мс</span>" +
        "</div>" +
        '<div class="hostline">' + item.host + ":" + item.port + "</div>" +
        '<div class="keyline">' + item.key + "</div>" +
      "</div>" +
      '<button class="copy-btn" onclick="copyText(\'' + encodeKey(item.key) + '\', this)">Копировать</button>' +
    "</article>"
  );
}

function renderList(data) {
  const entries = data.top15 || [];
  const container = document.getElementById("entries");

  if (!entries.length) {
    container.innerHTML = '<div class="empty-state">Рабочих ключей пока нет. Следующая проверка обновит рейтинг.</div>';
    return;
  }

  container.innerHTML = entries.map(renderEntry).join("");
}

function applyDownloads(data) {
  const downloads = data.downloads || FALLBACK_DOWNLOADS;
  document.getElementById("top15-link").href = downloads.top15 || FALLBACK_DOWNLOADS.top15;
  document.getElementById("full-link").href = downloads.full || FALLBACK_DOWNLOADS.full;
}

function renderMeta(data) {
  const totals = data.totals || {};
  setText("updated", data.updated_at_msk ? "Обновлено: " + data.updated_at_msk : "Обновление недоступно");
  setText("announce", data.announce || "Анонс недоступен");
  setText("working-count", totals.working ?? "—");
  setText("top-count", totals.top15 ?? "—");
  setText("unique-count", totals.unique ?? "—");
  setText("unsupported-count", totals.unsupported ?? "—");

  const unsupported = data.unsupported_reasons || {};
  const skipped = Object.entries(unsupported)
    .map(([reason, count]) => reason + ": " + count)
    .join(" · ");

  const statusParts = [];
  statusParts.push(data.check_mode === "tcp" ? "Проверка через TCP connect" : "Проверка через sing-box + generate_204");
  if (skipped) {
    statusParts.push("Пропущено: " + skipped);
  }
  document.getElementById("status-line").textContent = statusParts.join(" • ");
}

async function loadData() {
  try {
    const response = await fetch(KEYS_URL + "?t=" + Date.now());
    if (!response.ok) {
      throw new Error("Ошибка загрузки JSON");
    }

    const data = await response.json();
    renderMeta(data);
    applyDownloads(data);
    renderList(data);
  } catch (error) {
    setText("updated", "Ошибка загрузки данных");
    setText("announce", "Попробуйте обновить страницу позже");
    document.getElementById("status-line").textContent = "Не удалось загрузить актуальный рейтинг";
    document.getElementById("entries").innerHTML =
      '<div class="empty-state">JSON с результатами сейчас недоступен.</div>';
  }
}

function copyText(text, button) {
  navigator.clipboard.writeText(text).then(() => {
    const originalText = button.textContent;
    button.textContent = "Скопировано";
    setTimeout(() => {
      button.textContent = originalText;
    }, 1500);
  });
}

loadData();
