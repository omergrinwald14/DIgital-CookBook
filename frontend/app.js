// Frontend behavior — talks to the backend and renders the result.
// Separate from index.html so structure (HTML) and logic (JS) don't mix.

const API_BASE = "http://127.0.0.1:8000"; // backend dev server

// Track which chip is highlighted, so we can clear it when another is clicked.
let activeChip = null;
function setActiveChip(li) {
  if (activeChip) activeChip.classList.remove("active");
  activeChip = li;
  li.classList.add("active");
}

// Build one clickable category chip. If categoryId is given, add a ✕ to delete it.
function makeChip(label, onClick, categoryId = null) {
  const li = document.createElement("li");
  const text = document.createElement("span");
  text.textContent = label;
  li.appendChild(text);
  li.addEventListener("click", () => { setActiveChip(li); onClick(); });
  if (categoryId !== null) {
    const del = document.createElement("button");
    del.className = "chip-delete";
    del.textContent = "×";
    del.title = `Delete "${label}"`;
    del.addEventListener("click", (e) => {
      e.stopPropagation();                 // don't also trigger the filter
      deleteCategory(categoryId, label);
    });
    li.appendChild(del);
  }
  return li;
}

// Fetch the category list and paint it as clickable filter chips.
async function loadCategories() {
  const list = document.getElementById("category-list");
  try {
    const res = await fetch(`${API_BASE}/categories`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const categories = await res.json();
    list.innerHTML = ""; // clear "Loading…"
    const all = makeChip("All", () => loadRecipes()); // clears the filter
    list.appendChild(all);
    setActiveChip(all); // "All" highlighted on load
    for (const cat of categories) {
      list.appendChild(makeChip(cat.name, () => loadRecipes(cat.name), cat.id));
    }
  } catch (err) {
    list.textContent = `Could not load categories: ${err.message}`;
  }
}

// Fetch recipes (optionally filtered by category) and render each as a card.
async function loadRecipes(category = null) {
  const container = document.getElementById("recipe-list");
  container.textContent = "Loading…";
  try {
    const url = category
      ? `${API_BASE}/recipes?category=${encodeURIComponent(category)}`
      : `${API_BASE}/recipes`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const recipes = await res.json();
    container.innerHTML = ""; // clear "Loading…"
    if (recipes.length === 0) {
      container.textContent = "No recipes in this category yet.";
      return;
    }
    for (const recipe of recipes) {
      container.appendChild(renderRecipeCard(recipe));
    }
  } catch (err) {
    container.textContent = `Could not load recipes: ${err.message}`;
  }
}

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

// Build one recipe card. Uses textContent/attributes (not innerHTML) so
// caption-derived text can't inject markup (XSS-safe).
function renderRecipeCard(recipe) {
  const card = document.createElement("article");
  card.className = "recipe-card";

  if (recipe.thumbnail) {
    const img = document.createElement("img");
    img.src = recipe.thumbnail;
    img.alt = recipe.title || "Recipe";
    card.appendChild(img);
  }

  const title = document.createElement("h3");
  title.textContent = recipe.title || "Untitled";
  card.appendChild(title);

  const category = document.createElement("p");
  category.className = "recipe-category";
  category.textContent = recipe.categories?.name || "Unknown";
  card.appendChild(category);

  if (recipe.source_url) {
    const link = document.createElement("a");
    link.href = recipe.source_url;
    link.textContent = "Watch on Instagram";
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

// Create a category from the add form, then refresh the chips.
async function addCategory(event) {
  event.preventDefault();           // don't reload the page on submit
  const input = document.getElementById("new-category-name");
  const name = input.value.trim();
  if (!name) return;                // ignore empty; backend also guards (400)
  try {
    const res = await fetch(`${API_BASE}/categories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    input.value = "";               // clear the box
    await loadCategories();         // repaint chips, now including the new one
  } catch (err) {
    alert(`Could not add category: ${err.message}`);
  }
}

document.getElementById("add-category-form").addEventListener("submit", addCategory);

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
    const res = await fetch(`${API_BASE}/import`, {
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

// Remove a category (after confirm), then refresh chips + recipes.
async function deleteCategory(id, label) {
  if (!confirm(`Delete "${label}"? Its recipes will move to Unknown.`)) return;
  try {
    const res = await fetch(`${API_BASE}/categories/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await loadCategories();   // repaint chips without the deleted one
    await loadRecipes();      // recipes may have moved to Unknown
  } catch (err) {
    alert(`Could not delete category: ${err.message}`);
  }
}

loadCategories();
loadRecipes();
