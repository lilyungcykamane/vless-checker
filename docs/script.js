const KEYS_URL = "keys.json";
const REPO = "lilyungcykamane/vless-checker";
const FILES = { top100: "top100.txt", full: "good.txt" };

const links = {};

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function buildLinks(kind) {
  const file = FILES[kind];
  return {
    jsdelivr: `https://cdn.jsdelivr.net/gh/${REPO}/${file}`,
    github: `https://raw.githubusercontent.com/${REPO}/refs/heads/main/${file}`,
  };
}

function formatNumber(value) {
  return Number.isFinite(Number(value)) ? String(value) : "—";
}

function plural(count, one, few, many) {
  const tail = Math.abs(count) % 100;
  if (tail > 10 && tail < 20) {
    return many;
  }
  const last = tail % 10;
  if (last === 1) {
    return one;
  }
  return last >= 2 && last <= 4 ? few : many;
}

function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(number % 1 ? 1 : 0)}%` : "—";
}

function formatLatency(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number)} мс` : "—";
}

function renderStats(totals) {
  const cards = [
    ["Рабочих", totals.working],
    ["В ТОП-100", totals.top100],
    ["Проверено", totals.eligible],
    ["Отбраковано", totals.failed],
  ];

  document.getElementById("stats").innerHTML = cards
    .map(([label, value]) => `<div class="stat"><span>${label}</span><strong>${formatNumber(value)}</strong></div>`)
    .join("");
}

function renderEntries(entries) {
  const container = document.getElementById("entries");

  if (!entries.length) {
    container.innerHTML = '<p class="empty">Рабочих конфигов сейчас нет. Следующая проверка обновит список.</p>';
    return;
  }

  container.innerHTML = entries
    .map((item) => {
      const facts = [
        `${item.transport}+${item.security}`,
        `${formatPercent(item.availability_pct)} доступность`,
        `${formatNumber(item.success_streak)} ${plural(item.success_streak, "успех", "успеха", "успехов")} подряд`,
        formatLatency(item.median_latency_ms),
      ].join(" · ");

      return (
        '<div class="entry">' +
        `<div class="rank">${item.rank}</div>` +
        '<div class="entry-body">' +
        `<div class="entry-name">${item.name}${item.stable_qualified ? ' <span class="ok">стабилен</span>' : ""}</div>` +
        `<div class="entry-facts">${facts}</div>` +
        "</div>" +
        `<button type="button" data-config="${item.rank}">Копировать</button>` +
        "</div>"
      );
    })
    .join("");

  container.querySelectorAll("button[data-config]").forEach((button) => {
    const entry = entries[Number(button.dataset.config) - 1];
    button.addEventListener("click", () => copy(button, entry.key));
  });
}

function renderStatus(data) {
  const parts = [];
  if (data.check_mode === "xray") {
    parts.push("Проверка: Xray поднимает конфиг, через туннель уходит HTTP-запрос");
  }
  const ranking = data.ranking || {};
  if (ranking.min_availability_pct) {
    parts.push(
      `«Стабилен» — не меньше ${ranking.min_observations} ${plural(ranking.min_observations, "проверки", "проверок", "проверок")}, ` +
        `${ranking.min_availability_pct}% доступности и ${ranking.min_success_streak} ${plural(ranking.min_success_streak, "успех", "успеха", "успехов")} подряд`
    );
  }
  setText("status-line", parts.join(". "));
}

function copy(button, text) {
  navigator.clipboard.writeText(text).then(() => {
    const original = button.textContent;
    button.textContent = "Скопировано";
    button.classList.add("done");
    setTimeout(() => {
      button.textContent = original;
      button.classList.remove("done");
    }, 1500);
  });
}

function initSubscriptionButtons() {
  document.querySelectorAll(".sub").forEach((row) => {
    const kind = row.dataset.kind;
    links[kind] = buildLinks(kind);
    row.querySelectorAll("button[data-copy]").forEach((button) => {
      button.addEventListener("click", () => copy(button, links[kind][button.dataset.copy]));
    });
  });
}

async function load() {
  try {
    const response = await fetch(`${KEYS_URL}?t=${Date.now()}`);
    if (!response.ok) {
      throw new Error("keys.json недоступен");
    }

    const data = await response.json();
    setText("updated", data.updated_at_msk ? `Обновлено: ${data.updated_at_msk}` : "Время обновления неизвестно");
    renderStats(data.totals || {});
    renderStatus(data);
    renderEntries(data.top100 || []);
  } catch (error) {
    setText("updated", "Не удалось загрузить результаты проверки");
    setText("status-line", "Ссылки на подписки выше работают независимо от этой страницы.");
    document.getElementById("entries").innerHTML = '<p class="empty">Данные сейчас недоступны.</p>';
  }
}

initSubscriptionButtons();
load();
