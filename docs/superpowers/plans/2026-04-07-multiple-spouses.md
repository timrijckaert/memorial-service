# Multiple Spouses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `spouse` field with a `spouses` array so memorial cards with multiple marriages capture all spouse names.

**Architecture:** Four files change in lockstep: the JSON schema constant, the LLM extraction prompt, the review UI HTML/JS, and the test fixtures. No migration of existing data.

**Tech Stack:** Python, Ollama (JSON schema for structured output), vanilla HTML/JS/CSS, pytest

---

### Task 1: Update the JSON schema and test fixture

**Files:**
- Modify: `src/extract.py:28` (schema property)
- Modify: `src/extract.py:39` (required list)
- Modify: `tests/test_interpret.py:20` (sample response fixture)

- [ ] **Step 1: Update `PERSON_SCHEMA` in `src/extract.py`**

In `src/extract.py`, replace line 28:

```python
                "spouse": {"type": ["string", "null"]},
```

with:

```python
                "spouses": {"type": "array", "items": {"type": "string"}},
```

Then replace line 39 (the `required` list):

```python
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouse", "parents",
```

with:

```python
                "first_name", "last_name", "birth_date", "birth_place",
                "death_date", "death_place", "age_at_death", "spouses", "parents",
```

- [ ] **Step 2: Update `SAMPLE_LLM_RESPONSE` in `tests/test_interpret.py`**

In `tests/test_interpret.py`, replace line 20:

```python
        "spouse": "Amelia Gees",
```

with:

```python
        "spouses": ["Amelia Gees"],
```

- [ ] **Step 3: Run the interpret tests**

Run: `python -m pytest tests/test_interpret.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/extract.py tests/test_interpret.py
git commit -m "feat: rename spouse to spouses array in schema and test fixture"
```

---

### Task 2: Update the extraction prompt

**Files:**
- Modify: `prompts/extract_person.txt`

- [ ] **Step 1: Update spouse instructions in the IMPORTANT RULES section**

In `prompts/extract_person.txt`, replace line 15:

```
- For spouse: extract the full name as a single string. Set to null if not mentioned.
```

with:

```
- For spouses: extract the full name of every spouse as a list of strings, in marriage order (1st marriage first). Set to an empty list [] if no spouse is mentioned. When the text mentions multiple marriages (e.g. "weduwe in 't 1e huwelijk van X, in 't 2e huwelijk van Y"), include ALL spouse names — do not relegate later marriages to notes.
```

- [ ] **Step 2: Update the OUTPUT FIELDS section**

In `prompts/extract_person.txt`, replace line 32:

```
- spouse: Full name of spouse (husband/wife)
```

with:

```
- spouses: List of full spouse names in marriage order (1st marriage first). Empty list if none.
```

- [ ] **Step 3: Commit**

```bash
git add prompts/extract_person.txt
git commit -m "feat: update extraction prompt for spouses array"
```

---

### Task 3: Update the Review UI — HTML and CSS

**Files:**
- Modify: `src/review.py:169-174` (CSS)
- Modify: `src/review.py:206` (HTML form)

- [ ] **Step 1: Add CSS for the spouses list**

In `src/review.py`, replace the line:

```
  .no-image { color: #888; font-style: italic; }
```

with:

```
  .no-image { color: #888; font-style: italic; }
  .spouse-entry { display: flex; gap: 6px; margin-bottom: 6px; }
  .spouse-entry input { flex: 1; padding: 8px 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
  .spouse-entry input:focus { outline: none; border-color: #4a90d9; }
  .spouse-entry button { padding: 4px 10px; border: 1px solid #ddd; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; color: #999; }
  .spouse-entry button:hover { background: #fee; color: #c00; border-color: #c00; }
  .add-spouse-btn { padding: 6px 12px; border: 1px dashed #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; color: #666; }
  .add-spouse-btn:hover { border-color: #4a90d9; color: #4a90d9; }
```

- [ ] **Step 2: Replace the spouse form field with a spouses container**

In `src/review.py`, replace the line:

```
    <div class="form-group"><label>Spouse</label><input id="f-spouse"></div>
```

with:

```
    <div class="form-group"><label>Spouses</label><div id="spouses-list"></div><button type="button" class="add-spouse-btn" onclick="addSpouseInput('')">+ Add spouse</button></div>
```

- [ ] **Step 3: Commit**

```bash
git add src/review.py
git commit -m "feat: update review UI HTML/CSS for spouses list"
```

---

### Task 4: Update the Review UI — JavaScript

**Files:**
- Modify: `src/review.py` (JS in `REVIEW_HTML`)

- [ ] **Step 1: Add the `addSpouseInput` and `removeSpouseInput` functions**

In `src/review.py`, in the `<script>` block, add after the line `let currentSide = "back";`:

```javascript

function addSpouseInput(value) {
  const container = document.getElementById("spouses-list");
  const div = document.createElement("div");
  div.className = "spouse-entry";
  const input = document.createElement("input");
  input.value = value;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "\u00d7";
  btn.onclick = function() { div.remove(); };
  div.appendChild(input);
  div.appendChild(btn);
  container.appendChild(div);
}

function removeAllSpouseInputs() {
  document.getElementById("spouses-list").innerHTML = "";
}

function getSpousesFromForm() {
  const inputs = document.querySelectorAll("#spouses-list .spouse-entry input");
  const names = [];
  inputs.forEach(function(input) {
    const v = input.value.trim();
    if (v) names.push(v);
  });
  return names;
}
```

- [ ] **Step 2: Update `loadCard` to populate the spouses list**

In `src/review.py`, replace the line:

```javascript
  document.getElementById("f-spouse").value = p.spouse || "";
```

with:

```javascript
  removeAllSpouseInputs();
  (p.spouses || []).forEach(function(name) { addSpouseInput(name); });
  if (!p.spouses || p.spouses.length === 0) addSpouseInput("");
```

- [ ] **Step 3: Update `approveCard` to collect spouses from the form**

In `src/review.py`, replace the line:

```javascript
      spouse: document.getElementById("f-spouse").value.trim() || null,
```

with:

```javascript
      spouses: getSpousesFromForm(),
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/review.py
git commit -m "feat: update review UI JavaScript for spouses list"
```
