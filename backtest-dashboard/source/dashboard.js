(function () {
  "use strict";

  const root = document.documentElement;
  const storageKey = "backtest-theme";

  function readTheme() {
    try { return localStorage.getItem(storageKey); } catch (_) { return null; }
  }

  function writeTheme(value) {
    try { localStorage.setItem(storageKey, value); } catch (_) { /* file:// privacy modes */ }
  }

  function applyTheme(value) {
    root.dataset.theme = value;
    root.style.colorScheme = value;
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      const dark = value === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.setAttribute("aria-label", "Switch to " + (dark ? "light" : "dark") + " mode");
      button.querySelector("span").textContent = dark ? "☀" : "☾";
      button.querySelector("b").textContent = dark ? "Light" : "Dark";
    });
  }

  applyTheme(readTheme() === "dark" ? "dark" : "light");
  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(next);
      writeTheme(next);
    });
  });

  const master = document.querySelector("[data-master-dashboard]");
  if (master) {
    const rows = Array.from(master.querySelectorAll("tbody [data-fund-result]"));
    const cards = Array.from(master.querySelectorAll(".mobile-results [data-fund-result]"));
    const search = master.querySelector("[data-search]");
    const directionButton = master.querySelector("[data-direction]");
    const count = master.querySelector("[data-result-count]");
    const empty = master.querySelector("[data-empty-results]");
    let sortKey = "latest";
    let direction = "desc";

    function numeric(item) {
      const value = Number(item.dataset[sortKey]);
      return Number.isFinite(value) ? value : null;
    }

    function compare(a, b) {
      const av = numeric(a);
      const bv = numeric(b);
      if (av === null && bv !== null) return 1;
      if (av !== null && bv === null) return -1;
      if (av !== null && bv !== null && av !== bv) return direction === "asc" ? av - bv : bv - av;
      return a.dataset.code.localeCompare(b.dataset.code);
    }

    function update() {
      const query = search.value.trim().toLowerCase();
      const tableBody = master.querySelector("tbody");
      const cardContainer = master.querySelector(".mobile-results");
      rows.sort(compare).forEach(function (row) { tableBody.appendChild(row); });
      cards.sort(compare).forEach(function (card) { cardContainer.appendChild(card); });
      let visible = 0;
      rows.forEach(function (row, index) {
        const show = !query || row.dataset.search.includes(query);
        row.classList.toggle("is-hidden", !show);
        if (show) { visible += 1; row.querySelector("[data-rank]").textContent = "#" + visible; }
      });
      let mobileRank = 0;
      cards.forEach(function (card) {
        const show = !query || card.dataset.search.includes(query);
        card.classList.toggle("is-hidden", !show);
        if (show) { mobileRank += 1; card.querySelector("[data-rank]").textContent = "#" + mobileRank; }
      });
      count.textContent = visible;
      empty.hidden = visible !== 0;
    }

    search.addEventListener("input", update);
    master.querySelectorAll("[data-sort]").forEach(function (button) {
      button.addEventListener("click", function () {
        sortKey = button.dataset.sort;
        master.querySelectorAll("[data-sort]").forEach(function (item) { item.classList.toggle("selected", item === button); });
        update();
      });
    });
    directionButton.addEventListener("click", function () {
      direction = direction === "desc" ? "asc" : "desc";
      directionButton.textContent = direction === "desc" ? "Highest first ↓" : "Lowest first ↑";
      update();
    });
    master.querySelectorAll("[data-preset]").forEach(function (button) {
      button.addEventListener("click", function () {
        sortKey = button.dataset.preset;
        direction = "desc";
        directionButton.textContent = "Highest first ↓";
        master.querySelectorAll("[data-sort]").forEach(function (item) { item.classList.toggle("selected", item.dataset.sort === sortKey); });
        update();
        document.getElementById("ranking").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
    master.querySelectorAll("[data-column]").forEach(function (checkbox) {
      checkbox.addEventListener("change", function () {
        document.querySelectorAll(".column-" + checkbox.dataset.column).forEach(function (cell) {
          cell.classList.toggle("column-hidden", !checkbox.checked);
        });
        const selected = master.querySelectorAll("[data-column]:checked").length + 3;
        master.querySelector("[data-column-count]").textContent = selected;
      });
    });
    update();
  }

  document.querySelectorAll("[data-tab-group]").forEach(function (group) {
    const tabs = Array.from(group.querySelectorAll('[role="tab"]'));
    group.addEventListener("keydown", function (event) {
      const current = tabs.indexOf(document.activeElement);
      if (current < 0) return;
      let next = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (current + 1) % tabs.length;
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (current - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== null) { event.preventDefault(); tabs[next].focus(); tabs[next].click(); }
    });
  });

  const excess = document.querySelector("[data-excess-dashboard]");
  if (excess) {
    const sources = Array.from(excess.querySelectorAll("[data-excess-source]"));
    const runs = Array.from(excess.querySelectorAll("[data-excess-run]"));
    const views = Array.from(excess.querySelectorAll("[data-excess-view]"));
    let source = "mixed";
    let run = "all";

    function updateExcess() {
      sources.forEach(function (button) {
        const selected = button.dataset.excessSource === source;
        button.setAttribute("aria-selected", String(selected));
      });
      runs.forEach(function (button) {
        const selected = button.dataset.excessRun === run;
        button.setAttribute("aria-selected", String(selected));
      });
      views.forEach(function (view) {
        view.hidden = !(view.dataset.source === source && view.dataset.run === run);
      });
    }

    sources.forEach(function (button) {
      button.addEventListener("click", function () { source = button.dataset.excessSource; updateExcess(); });
    });
    runs.forEach(function (button) {
      button.addEventListener("click", function () { run = button.dataset.excessRun; updateExcess(); });
    });
    updateExcess();
  }

  const buyhold = document.querySelector("[data-buyhold-dashboard]");
  if (buyhold) {
    const tabs = Array.from(buyhold.querySelectorAll("[data-buyhold-source]"));
    const views = Array.from(buyhold.querySelectorAll("[data-buyhold-view]"));
    let source = "mixed";
    function updateBuyhold() {
      tabs.forEach(function (tab) {
        const selected = tab.dataset.buyholdSource === source;
        tab.setAttribute("aria-selected", String(selected));
      });
      views.forEach(function (view) { view.hidden = view.dataset.source !== source; });
    }
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () { source = tab.dataset.buyholdSource; updateBuyhold(); });
    });
    updateBuyhold();
  }

  const chartPanel = document.querySelector("[data-chart-panel]");
  if (chartPanel) {
    const tabs = Array.from(chartPanel.querySelectorAll("[data-chart-tab]"));
    const frame = chartPanel.querySelector("[data-chart-frame]");
    const unavailable = chartPanel.querySelector("[data-chart-unavailable]");
    const image = frame.querySelector("img");
    const link = frame;
    const description = chartPanel.querySelector("[data-chart-description]");

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        if (tab.disabled) return;
        tabs.forEach(function (item) {
          const selected = item === tab;
          item.classList.toggle("selected", selected);
          item.setAttribute("aria-selected", String(selected));
        });
        description.textContent = tab.dataset.description;
        if (tab.dataset.src) {
          image.src = tab.dataset.src;
          image.alt = tab.dataset.alt;
          link.href = tab.dataset.src;
          frame.classList.remove("is-hidden");
          unavailable.classList.add("is-hidden");
        } else {
          frame.classList.add("is-hidden");
          unavailable.classList.remove("is-hidden");
        }
      });
    });
  }
}());
