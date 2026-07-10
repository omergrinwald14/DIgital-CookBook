// Frontend behavior — talks to the backend and renders the result.
// Separate from index.html so structure (HTML) and logic (JS) don't mix.

const API_BASE = "https://digital-cookbook-api.onrender.com"; // live backend (Render)

// Identity (5-3c): the user's email, typed once on the login screen and kept
// in localStorage. Family-trust model — the backend trusts the X-User header.
const USER_KEY = "cookbook-user";

// One seam for every backend call: inject the X-User header here, so all
// requests are identified the same way and a future auth upgrade (real
// tokens) only touches this function.
function apiFetch(path, options = {}) {
  const user = localStorage.getItem(USER_KEY);
  return fetch(`${API_BASE}${path}`, {
    ...options,
    // Caller headers spread LAST so an explicit X-User (e.g. a queued
    // share's original owner) beats the logged-in default.
    headers: { ...(user ? { "X-User": user } : {}), ...(options.headers || {}) },
  });
}

// Cache of tags (id+name), refreshed by loadTags(). Card pickers
// read this so each card can list every tag without its own fetch.
let tagsCache = [];

// Last-fetched recipe list. Search filters this in the browser — no refetch,
// so it stays instant even when the backend is cold.
let recipesCache = [];

// Track which chip is highlighted, so we can clear it when another is clicked.
let activeChip = null;
function setActiveChip(li) {
  if (activeChip) activeChip.classList.remove("active");
  activeChip = li;
  li.classList.add("active");
}

// Build one clickable tag chip. If tagId is given, add a ✕ to delete it.
function makeChip(label, onClick, tagId = null) {
  const li = document.createElement("li");
  const text = document.createElement("span");
  text.textContent = label;
  li.appendChild(text);
  li.addEventListener("click", () => { setActiveChip(li); onClick(); });
  if (tagId !== null) {
    const del = document.createElement("button");
    del.className = "chip-delete";
    del.textContent = "×";
    del.title = `Delete "${label}"`;
    del.addEventListener("click", (e) => {
      e.stopPropagation();                 // don't also trigger the filter
      deleteTag(tagId, label);
    });
    li.appendChild(del);
  }
  return li;
}

// Fetch the tag list and paint it as clickable filter chips.
async function loadTags() {
  const list = document.getElementById("tag-list");
  try {
    const res = await apiFetch("/categories");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const tags = await res.json();
    tagsCache = tags; // keep the cache in sync for card pickers
    list.innerHTML = ""; // clear "Loading…"
    const all = makeChip("All", () => loadRecipes()); // clears the filter
    list.appendChild(all);
    setActiveChip(all); // "All" highlighted on load
    // Special cross-tag collections (no id -> no delete button).
    list.appendChild(makeChip("★ Favorites", () => loadRecipes(null, "favorites")));
    list.appendChild(makeChip("🔖 Up Next", () => loadRecipes(null, "up_next")));
    const unknown = makeChip("Unknown", () => loadRecipes("Unknown"));
    unknown.classList.add("extra");
    list.appendChild(unknown);
    for (const tag of tags) {
      const chip = makeChip(tag.name, () => loadRecipes(tag.name), tag.id);
      chip.classList.add("extra");
      list.appendChild(chip);
    }
    // Progressive disclosure: chips past the three pinned ones hide behind
    // a More/Less toggle so tags don't swallow the screen.
    const toggle = document.createElement("li");
    toggle.textContent = "More ▾";
    toggle.addEventListener("click", () => {
      const collapsed = list.classList.toggle("collapsed");
      toggle.textContent = collapsed ? "More ▾" : "Less ▴";
    });
    list.appendChild(toggle);
    list.classList.add("collapsed");
  } catch (err) {
    list.textContent = `Could not load tags: ${err.message}`;
  }
}

// Fetch recipes (optionally filtered by category) and render each as a card.
async function loadRecipes(category = null, collection = null) {
  const container = document.getElementById("recipe-list");
  container.textContent = "Loading…";
  try {
    // Build an encoded query string; filter by category OR collection.
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (collection) params.set("collection", collection);
    const qs = params.toString();
    const res = await apiFetch(`/recipes${qs ? `?${qs}` : ""}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    recipesCache = await res.json();
    renderRecipes(applySearch(recipesCache));
  } catch (err) {
    container.textContent = `Could not load recipes: ${err.message}`;
  }
}

// Paint a list of recipes as cards (used by both fetch and search).
function renderRecipes(recipes) {
  const container = document.getElementById("recipe-list");
  container.innerHTML = ""; // clear "Loading…" / previous cards
  if (recipes.length === 0) {
    container.textContent = "No recipes here yet.";
    return;
  }
  for (const recipe of recipes) {
    container.appendChild(renderRecipeCard(recipe));
  }
}

// Narrow a recipe list by the search box: match title or ingredient names.
function applySearch(recipes) {
  const q = document.getElementById("search-box").value.trim().toLowerCase();
  if (!q) return recipes;
  return recipes.filter((r) =>
    (r.title || "").toLowerCase().includes(q) ||
    (r.ingredients || []).some((i) => (i.name || "").toLowerCase().includes(q))
  );
}

// Re-filter on every keystroke — pure in-browser work, so it's instant.
document.getElementById("search-box").addEventListener("input",
  () => renderRecipes(applySearch(recipesCache)));

// Format one ingredient: "320 g Spaghetti", "2 cloves Garlic", or just
// "Olive oil" when quantity/unit are null. filter(Boolean) drops the blanks.
function formatIngredient(ing) {
  return [ing.quantity, ing.unit, ing.name].filter(Boolean).join(" ");
}

// Build the collapsible details (ingredients + steps) for a recipe.
function renderDetails(recipe) {
  const details = document.createElement("div");
  details.className = "recipe-details";
  details.hidden = true; // collapsed until the card is clicked

  const ingTitle = document.createElement("h4");
  ingTitle.textContent = "Ingredients";
  details.appendChild(ingTitle);
  if (recipe.ingredients?.length) {
    const ul = document.createElement("ul");
    for (const ing of recipe.ingredients) {
      const li = document.createElement("li");
      li.textContent = formatIngredient(ing);
      li.dir = "auto";                 // Hebrew -> RTL, English -> LTR (per item)
      ul.appendChild(li);
    }
    details.appendChild(ul);
  } else {
    const p = document.createElement("p");
    p.textContent = "No ingredients listed.";
    details.appendChild(p);
  }

  const stepTitle = document.createElement("h4");
  stepTitle.textContent = "Steps";
  details.appendChild(stepTitle);
  if (recipe.steps?.length) {
    const ol = document.createElement("ol");
    for (const step of recipe.steps) {
      const li = document.createElement("li");
      li.textContent = step;
      li.dir = "auto";                 // Hebrew -> RTL, English -> LTR (per item)
      ol.appendChild(li);
    }
    details.appendChild(ol);
  } else {
    const p = document.createElement("p");
    p.textContent = "No steps listed.";
    details.appendChild(p);
  }
  return details;
}

// Build a flag toggle button for a recipe card (★ Favorites / 🔖 Up Next).
function makeFlagToggle(recipe, key, onGlyph, offGlyph, label) {
  const btn = document.createElement("button");
  btn.className = "flag-toggle";
  const render = () => {
    btn.textContent = recipe[key] ? onGlyph : offGlyph;
    btn.classList.toggle("active", recipe[key]);
    btn.title = recipe[key] ? `Remove from ${label}` : `Add to ${label}`;
  };
  render();
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();                  // don't expand the card
    btn.disabled = true;
    try {
      const res = await apiFetch(`/recipes/${recipe.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: !recipe[key] }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      recipe[key] = !recipe[key];          // reflect new state locally
      render();
    } catch (err) {
      alert(`Could not update: ${err.message}`);
    } finally {
      btn.disabled = false;
    }
  });
  return btn;
}

// Build the tag picker for a card: a <select> of Unknown + every
// tag + a "new tag" sentinel. Changing it PATCHes the recipe;
// the "new" option creates the tag first, then assigns it.
function makeTagPicker(recipe) {
  const select = document.createElement("select");
  select.className = "recipe-category";
  select.addEventListener("click", (e) => e.stopPropagation()); // don't toggle card

  const current = recipe.categories?.name || "Unknown";
  const NEW = "__new__";

  // Dedup with a Set so `current` always appears even if the cache lags.
  const names = [...new Set(["Unknown", current, ...tagsCache.map((t) => t.name)])];
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    if (name === current) opt.selected = true;
    select.appendChild(opt);
  }
  const newOpt = document.createElement("option");
  newOpt.value = NEW;
  newOpt.textContent = "＋ New tag…";
  select.appendChild(newOpt);

  select.addEventListener("change", async () => {
    let category = select.value;
    if (category === NEW) {
      const name = (prompt("New tag name:") || "").trim();
      if (!name) { select.value = current; return; } // cancelled
      // Only create it if it's genuinely new (avoids duplicate-insert errors).
      if (!tagsCache.some((t) => t.name === name)) {
        try {
          const res = await apiFetch("/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          await loadTags(); // refresh chips + cache with the new one
        } catch (err) {
          alert(`Could not create tag: ${err.message}`);
          select.value = current;
          return;
        }
      }
      category = name;
    }
    try {
      const res = await apiFetch(`/recipes/${recipe.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      recipe.categories = category === "Unknown" ? null : { name: category };
    } catch (err) {
      alert(`Could not change tag: ${err.message}`);
      select.value = current;
    }
  });

  return select;
}

// Build one recipe card. Uses textContent/attributes (not innerHTML) so
// caption-derived text can't inject markup (XSS-safe).
function renderRecipeCard(recipe) {
  const card = document.createElement("article");
  card.className = "recipe-card";

  const del = document.createElement("button");
  del.className = "recipe-delete";
  del.textContent = "×";
  del.title = "Delete recipe";
  del.addEventListener("click", async (e) => {
    e.stopPropagation();                       // don't expand the card
    if (!confirm(`Delete "${recipe.title || "this recipe"}"? This can't be undone.`)) return;
    del.disabled = true;
    try {
      const res = await apiFetch(`/recipes/${recipe.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      card.remove();                           // drop just this card from the view
    } catch (err) {
      alert(`Could not delete: ${err.message}`);
      del.disabled = false;
    }
  });
  card.appendChild(del);

  const edit = document.createElement("button");
  edit.className = "recipe-edit";
  edit.textContent = "✎";
  edit.title = "Edit recipe";
  edit.addEventListener("click", (e) => {
    e.stopPropagation();                       // don't expand the card
    card.replaceWith(renderEditForm(recipe));  // swap card -> edit form
  });
  card.appendChild(edit);

  if (recipe.thumbnail) {
    const img = document.createElement("img");
    img.referrerPolicy = "no-referrer";   // Instagram's CDN 403s cross-site referers
    img.src = recipe.thumbnail;
    img.alt = recipe.title || "Recipe";
    card.appendChild(img);
  }

  const title = document.createElement("h3");
  title.textContent = recipe.title || "Untitled";
  title.dir = "auto";                  // Hebrew -> RTL, English -> LTR (per title)
  card.appendChild(title);

  card.appendChild(makeTagPicker(recipe));

  const tools = document.createElement("div");
  tools.className = "recipe-tools";
  tools.appendChild(makeFlagToggle(recipe, "is_favorite", "★", "☆", "Favorites"));
  tools.appendChild(makeFlagToggle(recipe, "is_up_next", "🔖", "🔖", "Up Next"));
  card.appendChild(tools);

  if (recipe.source_url) {
    const link = document.createElement("a");
    link.href = recipe.source_url;
    link.textContent = "Watch Video";
    link.target = "_blank";   // open in a new tab
    link.rel = "noopener";    // don't expose our page to the opened tab
    link.addEventListener("click", (e) => e.stopPropagation()); // don't toggle
    card.appendChild(link);
  }

  const details = renderDetails(recipe);
  card.appendChild(details);
  card.addEventListener("click", () => { details.hidden = !details.hidden; });

  return card;
}

// Build the in-place edit form that temporarily replaces a recipe card.
// Ingredients/steps are edited as plain text, one per line. Edited
// ingredients are saved as name-only (quantity/unit null) — cards display
// the same either way, we just stop guessing structure from free text.
function renderEditForm(recipe) {
  const card = document.createElement("article");
  card.className = "recipe-card editing";
  const form = document.createElement("form");
  form.className = "edit-form";

  // Small helper: a labelled field, so the form reads top-to-bottom.
  function field(labelText, el) {
    const label = document.createElement("label");
    label.textContent = labelText;
    label.appendChild(el);
    form.appendChild(label);
  }

  const titleIn = document.createElement("input");
  titleIn.type = "text";
  titleIn.value = recipe.title || "";
  titleIn.dir = "auto";
  field("Title", titleIn);

  const ingIn = document.createElement("textarea");
  ingIn.rows = 6;
  ingIn.dir = "auto";
  ingIn.value = (recipe.ingredients || []).map(formatIngredient).join("\n");
  field("Ingredients (one per line)", ingIn);

  const stepsIn = document.createElement("textarea");
  stepsIn.rows = 8;
  stepsIn.dir = "auto";
  stepsIn.value = (recipe.steps || []).join("\n");
  field("Steps (one per line)", stepsIn);

  const buttons = document.createElement("div");
  buttons.className = "edit-buttons";
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save";
  const cancel = document.createElement("button");
  cancel.type = "button";                     // type=button: don't submit
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => {
    card.replaceWith(renderRecipeCard(recipe)); // discard edits, restore card
  });
  buttons.append(save, cancel);
  form.appendChild(buttons);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const toLines = (s) => s.split("\n").map((l) => l.trim()).filter(Boolean);
    const body = {
      title: titleIn.value.trim(),
      ingredients: toLines(ingIn.value).map((name) => ({ name, quantity: null, unit: null })),
      steps: toLines(stepsIn.value),
    };
    if (!body.title) { alert("Title cannot be empty."); return; }
    save.disabled = true;
    try {
      const res = await apiFetch(`/recipes/${recipe.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      Object.assign(recipe, body);              // reflect saved edits locally
      card.replaceWith(renderRecipeCard(recipe));
    } catch (err) {
      alert(`Could not save: ${err.message}`);
      save.disabled = false;
    }
  });

  card.appendChild(form);
  return card;
}

// Create a tag from the add form, then refresh the chips.
async function addTag(event) {
  event.preventDefault();           // don't reload the page on submit
  const input = document.getElementById("new-tag-name");
  const name = input.value.trim();
  if (!name) return;                // ignore empty; backend also guards (400)
  try {
    const res = await apiFetch("/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    input.value = "";               // clear the box
    await loadTags();               // repaint chips, now including the new one
  } catch (err) {
    alert(`Could not add tag: ${err.message}`);
  }
}

document.getElementById("add-tag-form").addEventListener("submit", addTag);

// Import a recipe from a pasted URL via POST /import (slow: fetch + LLM parse).
async function importRecipe(event) {
  event.preventDefault();
  const input = document.getElementById("import-url");
  const button = event.target.querySelector("button");
  const status = document.getElementById("import-status");
  const url = input.value.trim();
  if (!url) return;

  button.disabled = true;                       // prevent double-submit
  status.hidden = false;
  status.textContent = "Importing… this can take 10–30s.";
  try {
    const res = await apiFetch("/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const recipe = await res.json();
    input.value = "";
    status.textContent = `Added: ${recipe.title || "Untitled"}`;
    await loadRecipes();                         // show the new recipe
  } catch (err) {
    status.textContent = `Import failed: ${err.message}`;
  } finally {
    button.disabled = false;                     // always re-enable
  }
}

document.getElementById("import-form").addEventListener("submit", importRecipe);

// Remove a tag (after confirm), then refresh chips + recipes.
async function deleteTag(id, label) {
  if (!confirm(`Delete "${label}"? Its recipes will move to Unknown.`)) return;
  try {
    const res = await apiFetch(`/categories/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await loadTags();         // repaint chips without the deleted one
    await loadRecipes();      // recipes may have moved to Unknown
  } catch (err) {
    alert(`Could not delete tag: ${err.message}`);
  }
}

// Deliver queued shares from the page. Background Sync alone proved
// unreliable: Chrome stops retrying after ~3 attempts, and each attempt can
// die against Render's ~50s cold start — entries then sit in IndexedDB
// forever. Opening the app is now the guaranteed delivery path; the SW sync
// remains as a best-effort fast path. Mirrors sw.js's drop rule:
// ok or 4xx (retrying can't fix a bad URL) -> remove; 5xx/network -> keep.
async function drainPendingShares() {
  const banner = document.getElementById("pending-shares");
  let shares;
  try { shares = await listShares(); } catch { return; }  // IndexedDB unavailable
  if (!shares.length) return;
  banner.hidden = false;
  let saved = 0;
  for (const [i, share] of shares.entries()) {
    banner.textContent = `Saving ${shares.length} pending shared recipe(s)… (${i} done)`;
    try {
      // Queued entries carry who shared them; that owner wins over whoever
      // is logged in now (someone else may have opened the app since).
      const res = await apiFetch("/import", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(share.owner ? { "X-User": share.owner } : {}),
        },
        body: JSON.stringify({ url: share.url }),
      });
      if (res.ok || (res.status >= 400 && res.status < 500)) {
        await removeShare(share.id);
        if (res.ok) saved++;
      }
    } catch { /* offline / server down — keep queued for the next visit */ }
  }
  banner.textContent = saved
    ? `Saved ${saved} shared recipe(s).`
    : "Pending shares could not be saved — will retry on the next visit.";
  setTimeout(() => { banner.hidden = true; }, 6000);
  if (saved) await loadRecipes();
}

// Boot: tags first so card pickers have the cache; recipes render
// before the (possibly slow, cold-start) queue drain so the app is usable
// immediately.
function boot() {
  loadTags().then(loadRecipes).then(drainPendingShares);
}

// Login gate (5-3c): with a stored identity, boot straight in; without one,
// show the login screen and boot after the email is saved.
const loginScreen = document.getElementById("login-screen");
const userBadge = document.getElementById("user-badge");

function showUserBadge(email) {
  userBadge.textContent = email;
  userBadge.hidden = false;
}

// The badge doubles as "switch user": clear the identity and start over.
userBadge.addEventListener("click", () => {
  if (!confirm("Switch user? You'll be asked for an email again.")) return;
  localStorage.removeItem(USER_KEY);
  location.reload();
});

document.getElementById("login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  // Normalize (trim + lowercase) so "Omer@x" and "omer@x" are one cookbook.
  const email = document.getElementById("login-email").value.trim().toLowerCase();
  if (!email) return;
  localStorage.setItem(USER_KEY, email);
  loginScreen.hidden = true;
  showUserBadge(email);
  boot();
});

const storedUser = localStorage.getItem(USER_KEY);
if (storedUser) {
  showUserBadge(storedUser);
  boot();
} else {
  loginScreen.hidden = false;
}

// Install guide: auto-open the tab matching the visitor's phone; the tab
// pills let them switch anyway (covers iPads that report a Mac userAgent).
const installGuide = document.getElementById("install-guide");

function detectPlatform() {
  return /iPhone|iPad|iPod/.test(navigator.userAgent) ? "ios" : "android";
}

function selectGuideTab(platform) {
  document.getElementById("guide-android").hidden = platform !== "android";
  document.getElementById("guide-ios").hidden = platform !== "ios";
  document.querySelectorAll(".guide-tab").forEach((tab) =>
    tab.classList.toggle("active", tab.dataset.platform === platform)
  );
}

function openInstallGuide() {
  selectGuideTab(detectPlatform());
  installGuide.hidden = false;
}

document.getElementById("install-help").addEventListener("click", openInstallGuide);
document.getElementById("login-install-help").addEventListener("click", openInstallGuide);
document.getElementById("install-guide-close").addEventListener("click", () => {
  installGuide.hidden = true;
});
document.querySelectorAll(".guide-tab").forEach((tab) =>
  tab.addEventListener("click", () => selectGuideTab(tab.dataset.platform))
);

// Register the service worker (enables PWA install + Web Share Target).
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch((err) =>
    console.warn("SW registration failed:", err)
  );
}
