const KEYS_URL = "keys.json";
const FALLBACK_DOWNLOADS = {
  top100: "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top100.txt",
  top50: "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top50.txt",
  top15: "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/top15.txt",
  full: "https://cdn.jsdelivr.net/gh/lilyungcykamane/vless-checker/good.txt",
};
const VK_PLACEHOLDER_URL = "https://vk.com/id000";
let currentDownloads = { ...FALLBACK_DOWNLOADS };

function encodeKey(key) {
  return key.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (!element) {
    return;
  }
  element.textContent = value;
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return number.toFixed(number % 1 === 0 ? 0 : 1) + "%";
}

function formatLatency(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  return number.toFixed(number % 1 === 0 ? 0 : 1) + " мс";
}

function formatObservations(value) {
  if (Array.isArray(value)) {
    return String(value.length);
  }
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "object") {
    return String(Object.keys(value).length);
  }
  return String(value);
}

function renderEntry(item) {
  const availability = formatPercent(item.availability_pct);
  const streak = Number(item.success_streak);
  const streakLabel = Number.isFinite(streak) ? String(streak) : "—";
  const medianLatency = formatLatency(item.median_latency_ms);
  const currentLatency = formatLatency(item.latency_ms);
  const observations = formatObservations(item.observations);

  return (
    '<article class="entry">' +
      '<div class="entry-rank">#' + item.rank + '</div>' +
      '<div class="entry-main">' +
        '<div class="entry-topline">' +
          '<span class="country">' + (item.flag || "🌍") + " " + item.country + "</span>" +
          '<span class="stability">' + availability + " доступность</span>" +
          '<span class="streak">' + streakLabel + " подряд</span>" +
        "</div>" +
        '<div class="entry-metrics">' +
          '<div class="metric">' +
            '<span class="metric-label">Медиана</span>' +
            '<strong>' + medianLatency + '</strong>' +
          "</div>" +
          '<div class="metric">' +
            '<span class="metric-label">Последний чек</span>' +
            '<strong>' + currentLatency + '</strong>' +
          "</div>" +
          '<div class="metric">' +
            '<span class="metric-label">Наблюдений</span>' +
            '<strong>' + observations + "</strong>" +
          "</div>" +
      "</div>" +
        '<div class="hostline">' + item.host + ":" + item.port + "</div>" +
      "</div>" +
      '<button class="copy-btn" onclick="copyText(\'' + encodeKey(item.key) + '\', this)">Копировать</button>' +
    "</article>"
  );
}

function renderList(data) {
  const entries = data.top100 || data.top50 || data.top15 || [];
  const container = document.getElementById("entries");

  if (!entries.length) {
    container.innerHTML = '<div class="empty-state">Стабильных ключей пока нет. Следующая проверка обновит рейтинг.</div>';
    return;
  }

  container.innerHTML = entries.map(renderEntry).join("");
}

function parseDownloadUrl(url) {
  if (!url) {
    return null;
  }

  const jsdelivrMatch = url.match(/^https:\/\/cdn\.jsdelivr\.net\/gh\/([^/]+)\/([^/]+)\/(.+)$/);
  if (!jsdelivrMatch) {
    return null;
  }

  const [, owner, repo, path] = jsdelivrMatch;
  return { owner, repo, ref: "main", path };
}

function buildModalLinks(kind) {
  const parsed = parseDownloadUrl(currentDownloads[kind]);
  if (!parsed) {
    return null;
  }

  const { owner, repo, ref, path } = parsed;
  const raw = "https://raw.githubusercontent.com/" + owner + "/" + repo + "/refs/heads/" + ref + "/" + path;

  return {
    jsdelivr: currentDownloads[kind],
    yandex: "https://translate.yandex.ru/translate?url=" + raw + "&lang=de-de",
    github: raw,
  };
}

function setModalActionValue(id, mode, value) {
  const button = document.getElementById(id);
  if (!button) {
    return;
  }

  button.dataset.mode = mode;
  button.dataset.value = value;
}

function resetModalActionSubtitles() {
  document.querySelectorAll(".modal-action-subtitle").forEach((subtitle) => {
    if (subtitle.dataset.originalText) {
      subtitle.textContent = subtitle.dataset.originalText;
    }
  });
}

function openDownloadModal(kind) {
  const links = buildModalLinks(kind);
  if (!links) {
    return;
  }

  const title = kind === "top100" ? "Подписка ТОП100" : "Подписка полная";
  resetModalActionSubtitles();
  setText("download-modal-title", title);
  setText("download-modal-text", "Выберите способ получение подписки:");
  setModalActionValue("download-jsdelivr", "copy", links.jsdelivr);
  setModalActionValue("download-yandex", "open", links.yandex);
  setModalActionValue("download-vk", "open", VK_PLACEHOLDER_URL);
  setModalActionValue("download-github", "copy", links.github);
  document.getElementById("download-modal").hidden = false;
  document.body.classList.add("modal-open");
}

function closeDownloadModal() {
  document.getElementById("download-modal").hidden = true;
  document.body.classList.remove("modal-open");
}

function renderMeta(data) {
  const totals = data.totals || {};
  setText("updated", data.updated_at_msk ? "Обновлено: " + data.updated_at_msk : "Обновление недоступно");
  setText("working-count", totals.working ?? "—");
  setText("top-count", totals.top100 ?? totals.top50 ?? totals.top15 ?? "—");
  setText("unique-count", totals.unique ?? "—");
  setText("unsupported-count", totals.unsupported ?? "—");

  const unsupported = data.unsupported_reasons || {};
  const skipped = Object.entries(unsupported)
    .map(([reason, count]) => reason + ": " + count)
    .join(" · ");

  const statusParts = [];
  statusParts.push(data.check_mode === "tcp" ? "Проверка через TCP connect" : "Проверка через sing-box + generate_204");
  statusParts.push("Рейтинг построен по стабильности: availability, streak и история чеков");
  if (skipped) {
    statusParts.push("Пропущено: " + skipped);
  }
  document.getElementById("status-line").textContent = statusParts.join(" • ");
}

function applyDownloads(data) {
  const downloads = data.downloads || FALLBACK_DOWNLOADS;
  currentDownloads = {
    top100: downloads.top100 || downloads.top50 || downloads.top15 || FALLBACK_DOWNLOADS.top100,
    top50: downloads.top50 || downloads.top15 || FALLBACK_DOWNLOADS.top50,
    top15: downloads.top15 || FALLBACK_DOWNLOADS.top15,
    full: downloads.full || FALLBACK_DOWNLOADS.full,
  };
}

async function loadData() {
  try {
    const response = await fetch(KEYS_URL + "?t=" + Date.now());
    if (!response.ok) {
      throw new Error("Ошибка загрузки JSON");
    }

    const data = await response.json();
    applyDownloads(data);
    renderMeta(data);
    renderList(data);
  } catch (error) {
    setText("updated", "Ошибка загрузки данных");
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

function flashModalSubtitle(button, message) {
  const subtitle = button.querySelector(".modal-action-subtitle");
  if (!subtitle) {
    return;
  }

  const originalText = subtitle.dataset.originalText || subtitle.textContent;
  subtitle.dataset.originalText = originalText;
  subtitle.textContent = message;
  setTimeout(() => {
    subtitle.textContent = originalText;
  }, 1600);
}

function copyDownloadLink(button, value) {
  navigator.clipboard.writeText(value).then(() => {
    flashModalSubtitle(button, "Ссылка скопирована");
  });
}

function openDownloadLink(button, value) {
  flashModalSubtitle(button, "Открываем ссылку");
  window.open(value, "_blank", "noopener,noreferrer");
}

function handleModalAction(button) {
  const value = button.dataset.value;
  const mode = button.dataset.mode;
  if (!value || !mode) {
    return;
  }

  if (mode === "copy") {
    copyDownloadLink(button, value);
    return;
  }

  if (mode === "open") {
    openDownloadLink(button, value);
  }
}

document.getElementById("top100-link").addEventListener("click", () => {
  openDownloadModal("top100");
});

document.getElementById("full-link").addEventListener("click", () => {
  openDownloadModal("full");
});

document.getElementById("download-modal-close").addEventListener("click", closeDownloadModal);

document.getElementById("download-modal").addEventListener("click", (event) => {
  if (event.target.id === "download-modal") {
    closeDownloadModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDownloadModal();
  }
});

document.querySelectorAll(".modal-action").forEach((button) => {
  button.addEventListener("click", () => {
    handleModalAction(button);
  });
});

closeDownloadModal();
loadData();
