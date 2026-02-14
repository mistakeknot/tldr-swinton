# User Experience Review: ColBERT Late-Interaction Search Backend Plan

**Reviewer:** Flux-drive User & Product Reviewer
**Plan:** `docs/plans/2026-02-14-colbert-search-backend.md`
**Date:** 2026-02-14
**Primary User:** Python developers using tldr-swinton for semantic code search

## User Context

**Primary Job-to-be-Done:** Find relevant code quickly using natural language queries (e.g., "authentication logic", "file upload handling") instead of browsing files or grepping.

**User Segments:**
- **Existing users** with FAISS indexes who may want better search quality
- **New users** installing tldr-swinton for the first time
- **MCP/daemon users** expecting fast, always-available search
- **CI/automation users** where cold-start latency compounds across multiple invocations

## Critical UX Issues

### 1. 17-Second Cold Start — High-Severity Blocker

**Problem:** First query after daemon start takes ~17s (model loading). This is the worst possible moment for latency — the user's first interaction with the new feature.

**User Impact:**
- **New user trying ColBERT for the first time:** Types `tldrs find "auth logic"`, waits 17 seconds, assumes it's broken or hangs. No feedback loop explaining the delay.
- **Daemon restart scenario:** Daemon crashes/restarts mid-session → next query hangs for 17s with no warning.
- **MCP tool calls:** Claude Code invokes semantic search → 17s pause with no visible feedback. Claude may timeout or user cancels thinking it's stuck.

**Missing UX Affordances:**
1. **No pre-warming guidance.** Plan mentions "Pre-warm on daemon start; lazy load in non-daemon CLI" but doesn't specify **how users trigger pre-warming** or **when lazy-load happens**.
2. **No progress feedback during model load.** 17 seconds is long enough that users need a "Loading ColBERT model..." message.
3. **No CLI flag to force pre-warming.** Users can't proactively warm the cache before real work.

**Recommended Mitigations:**
- **Daemon auto-warms on startup** (not lazy). Start model load in background thread during daemon init, emit log line.
- **CLI shows spinner during first-query load:** `"Loading ColBERT model (first query only, ~17s)..."`
- **Add `tldrs semantic warmup` command** to explicitly pre-load model without running a search.
- **Document the cold-start behavior prominently** in install docs and `--help` text.

**Severity:** **HIGH** — This will cause adoption drop-off if users hit it before understanding the value proposition.

---

### 2. Backend Auto-Detection Creates Invisible Quality Divergence

**Problem:** `backend="auto"` silently picks ColBERT if pylate is installed, FAISS otherwise. Users don't know which backend answered their query unless they check logs or `--info`.

**User Impact:**
- **Quality expectations unclear:** If ColBERT is "better" (per the plan's motivation), users on FAISS will get worse results without knowing why.
- **Inconsistent results across environments:** Developer's laptop has pylate → uses ColBERT. CI environment doesn't → uses FAISS. Search results differ, no obvious explanation.
- **Debugging difficulty:** User reports "search doesn't find X" — is it the query, the index, or the backend?

**Missing Affordances:**
1. **No indication which backend was used.** Search output should show `[Backend: colbert]` or similar.
2. **No warning when falling back to FAISS.** User installs `[semantic-colbert]`, forgets to rebuild index → searches use old FAISS index silently.
3. **No guidance on when to rebuild.** Plan says "users rebuild with `tldrs semantic index --backend=colbert`" but doesn't explain **why** or **when** they should do this.

**Recommended Mitigations:**
- **Show backend in search output header:** `Searching with ColBERT (17M params)...` or `Searching with FAISS (768d vectors)...`
- **Warn on backend mismatch:** If index was built with FAISS but pylate is now installed, emit: `"Index was built with FAISS. Rebuild with --backend=colbert for better quality."`
- **Add backend to `tldrs index --info` output prominently** (plan already mentions this, good).
- **Document quality trade-offs explicitly** in README/AGENTS.md: "ColBERT provides X% better recall on CoIR benchmarks."

**Severity:** **MEDIUM** — Doesn't block usage but creates confusion and hidden quality regressions.

---

### 3. No Migration Path for Existing Users

**Problem:** Plan states "Existing FAISS indexes are NOT migrated — users rebuild." This is technically correct but **ignores the user-side friction**.

**User Impact:**
- **Existing user upgrades to get ColBERT:** Runs `pip install 'tldr-swinton[semantic-colbert]'`, expects immediate benefit. Runs `tldrs find "auth"` → still uses old FAISS index (because `--backend=auto` loads what exists, not what's preferred).
- **No proactive nudge to rebuild.** User never learns ColBERT is available unless they read changelog or re-run `--help`.
- **Index size grows:** FAISS index in `.tldrs/index/`, PLAID index in `.tldrs/index/plaid/`. No cleanup guidance. Users with large repos (10k+ files) now have 2x storage.

**Missing Affordances:**
1. **No version detection in index metadata.** Can't tell if index is "old FAISS" vs "new FAISS post-upgrade."
2. **No `tldrs semantic migrate` command** to automate FAISS → ColBERT transition.
3. **No storage cleanup guidance.** If user rebuilds with `--backend=colbert`, old FAISS files stay in `.tldrs/index/`.

**Recommended Mitigations:**
- **Add migration detection:** On first run after upgrade, check if FAISS index exists and pylate is available. Emit: `"ColBERT backend now available. Rebuild index for better search quality: tldrs semantic index --backend=colbert"`
- **Add `--clean` flag to `index` command:** Removes old backend's files when building with a different backend.
- **Document migration workflow prominently** in upgrade notes:
  1. `pip install 'tldr-swinton[semantic-colbert]'`
  2. `tldrs semantic index --backend=colbert --clean`
  3. (Optional) `du -sh .tldrs/index/` to verify old files are gone.

**Severity:** **MEDIUM** — Users can work around it but adoption of ColBERT will be lower than expected.

---

### 4. 1.7GB Install Weight for "Optional" Feature

**Problem:** `pip install 'tldr-swinton[semantic-colbert]'` pulls ~1.7GB PyTorch. Plan labels this as "optional extra" but doesn't address the **perception mismatch**.

**User Impact:**
- **Cognitive dissonance:** Feature is marketed as "better search quality" but requires massive dependency. Users wonder "Is this really optional if it's the preferred way?"
- **Environment constraints:** Users in Docker containers, CI environments, or bandwidth-limited networks may **reject the upgrade entirely** due to size.
- **No incremental adoption path.** It's all-or-nothing: either accept 1.7GB or stay on FAISS forever.

**Missing Affordances:**
1. **No size warning during install.** Users discover the 1.7GB download mid-install, can't cancel cleanly.
2. **No "try before commit" option.** Can't test ColBERT quality without full install.
3. **No guidance on alternative deployment models.** Could ColBERT run as a separate service (HTTP API) to share model across projects?

**Recommended Mitigations:**
- **Document install size prominently:** README should say `[semantic-colbert]` requires ~1.7GB PyTorch. Show both minimal and full install options side-by-side.
- **Provide quality comparison data** so users can decide if 1.7GB is worth it: "ColBERT improves recall by X% on our benchmark vs FAISS."
- **Consider ONNX/quantized model option** (future work) for smaller footprint (plan mentions this is future, good).
- **Pre-installation size check:** Add `tldrs semantic check-deps --backend=colbert` command that reports disk space required before install.

**Severity:** **LOW-MEDIUM** — Doesn't break UX but creates adoption friction for size-sensitive users.

---

### 5. Discoverability Gaps

**Problem:** Plan adds `--backend` flag to CLI and MCP tools but doesn't address **how users learn about the new backend**.

**User Impact:**
- **Existing users never try ColBERT** because they don't read changelogs.
- **New users default to FAISS** (via `--backend=auto` fallback) and never know ColBERT exists.
- **MCP users have no visibility** into backend choice — it's fully automated, no way to override or inspect.

**Missing Affordances:**
1. **No in-tool discovery mechanism.** Running `tldrs find` doesn't hint that a better backend exists.
2. **No quality metrics in output.** Users can't tell if their search results are "good" or "could be better."
3. **No A/B comparison tool.** Can't easily compare FAISS vs ColBERT results for the same query.

**Recommended Mitigations:**
- **Add setup hint on first run after upgrade:** `"Tip: Install tldr-swinton[semantic-colbert] for improved search quality (requires ~1.7GB)."`
- **Add `tldrs semantic compare` command** to run same query on both backends and show results side-by-side (requires both installed).
- **MCP tool documentation** should explain auto-detection behavior and how to inspect/override it.

**Severity:** **MEDIUM** — Feature exists but users won't find it organically.

---

## Flow Analysis

### Happy Path: New User Adopts ColBERT

1. User installs: `pip install 'tldr-swinton[semantic-colbert]'` → **No size warning, 1.7GB download surprises them**
2. User runs: `tldrs semantic index --backend=colbert` → **Works, but no progress feedback during model download**
3. User runs: `tldrs find "auth logic"` → **17s hang on first query, no feedback** → User cancels, thinks it's broken
4. User retries, waits through 17s → **Results appear, but no indication which backend was used**
5. User runs second query → **6ms, fast** → User is confused why first query was slow

**Failure Points:**
- Step 1: No size warning → user annoyed
- Step 3: No feedback during cold start → user gives up
- Step 4: No backend indication → user doesn't connect "fast second query" to "model now resident"

### Degraded Path: Existing User Upgrades

1. User installs: `pip install 'tldr-swinton[semantic-colbert]'` → **Expects automatic improvement**
2. User runs: `tldrs find "auth logic"` → **Uses old FAISS index (auto-detection picks existing backend)**
3. User sees no quality change → **Concludes upgrade was pointless, never rebuilds**

**Failure Points:**
- Step 2: No migration nudge → user never adopts ColBERT despite installing deps

### Error Path: Daemon Restart During Session

1. User starts daemon, runs search → **ColBERT model loaded (17s)**
2. Daemon crashes (unrelated bug) → **Model unloaded from memory**
3. User runs search again → **17s hang, no explanation** → User reports "search randomly hangs"

**Failure Points:**
- Step 3: No indication this is expected behavior → looks like a performance regression

---

## Product Validation

### Problem Definition

**Claimed Pain:** FAISS semantic search has lower quality than ColBERT late-interaction search.

**Evidence Quality:** **WEAK**
- Plan cites "MTEB Code v1: 66.64" for LateOn-Code-edge model but provides no comparative benchmark against current FAISS+nomic-embed-text-v2-moe setup.
- No user complaints or feature requests cited for "search quality insufficient."
- Memory note mentions "ColBERT is 1.8x larger storage" but no quality metric justifying the cost.

**Questions Unanswered:**
1. What percentage of current search queries would improve with ColBERT?
2. How many users are willing to pay 1.7GB install cost for quality improvement?
3. Is the quality gap large enough to justify cold-start friction?

### Solution Fit

**Does the plan address the stated problem?** YES — if search quality is indeed insufficient, ColBERT is a credible solution.

**Are there simpler alternatives?**
- **Tune FAISS parameters** (e.g., try IVF index instead of Flat, adjust k/nprobe) before adding second backend.
- **Improve query preprocessing** (e.g., expand abbreviations, synonym handling) to boost FAISS quality without new deps.
- **Hybrid search tuning** (plan adds BM25 fusion, good) — could this alone close the quality gap?

**Opportunity Cost:**
- Implementing dual backend adds **~800 lines of code** (protocol, two backends, factory, tests).
- Maintenance burden: both backends must be tested/updated for every format/flag change.
- Alternative use of dev time: improve diff-context compression, add more languages, optimize token efficiency.

### Success Criteria Missing

**What does success look like?**
- Plan has no measurable success signal. Should include:
  - "ColBERT improves recall@10 by ≥15% on tldr-bench semantic search tasks"
  - "≥50% of users with semantic-colbert installed rebuild indexes within 30 days"
  - "Cold-start feedback reduces user confusion (measured by support questions)"

**Validation Before Full Rollout:**
- Plan says "Ship as optional extra, validate, then make preferred" but doesn't specify validation criteria or timeline.
- Recommend: A/B test with 10 existing users, measure search quality and adoption friction before promoting to default.

---

## User Segmentation

| Segment | Value Proposition | Adoption Barriers | Net Impact |
|---------|-------------------|-------------------|------------|
| **New users (no existing index)** | Better search quality out of the box | 1.7GB install, 17s cold start | **NEUTRAL** — Will adopt if quality gap is clear and documented |
| **Existing users (FAISS index)** | Improved search results | Must rebuild index, no migration nudge, storage grows | **NEGATIVE** — Low adoption likely without proactive migration UX |
| **MCP/daemon users** | Transparent quality upgrade | Cold start on daemon restart, no control over backend | **NEGATIVE** — Latency regression looks like a bug |
| **CI/automation users** | N/A | 1.7GB install bloat, cold start on every run | **STRONGLY NEGATIVE** — Will not adopt |

**Highest Risk Segment:** Existing users with large indexes. Rebuilding a 10k-file repo can take 10+ minutes. No incremental migration = all-or-nothing decision.

---

## Terminal/CLI-Specific Concerns

### Keyboard Interaction

**No issues.** Plan doesn't add new key bindings or TUI modes.

### Error Messages

**Missing actionable guidance:**
- If `tldrs semantic index --backend=colbert` fails because pylate not installed, error should say: `"Backend 'colbert' requires pylate. Install with: pip install 'tldr-swinton[semantic-colbert]'"`
- If search finds no results, output should hint: `"No results found. Try rebuilding index or switching backend."`

### Help Text Quality

**Needs improvement:**
- `tldrs semantic index --help` should explain `--backend` values: `auto` (tries colbert, falls back to faiss), `colbert` (requires pylate), `faiss` (always available).
- Should also note: `"First search with colbert takes ~17s to load model."`

### Progress Disclosure

**Missing entirely:**
- 17s model load has no progress bar or spinner.
- Index rebuild with large repos has no ETA or file-count feedback.

---

## Evidence Standards

| Claim | Evidence Type | Quality |
|-------|--------------|---------|
| "ColBERT has better quality" | MTEB benchmark score | **WEAK** — No comparative test on tldr-swinton's actual workload |
| "17s cold start acceptable for daemon" | Assertion | **ASSUMPTION** — No user testing, no comparison to acceptable latency thresholds |
| "Users will rebuild indexes voluntarily" | Assumption | **ASSUMPTION** — No historical adoption data for similar migrations |
| "1.7GB is acceptable for 'optional' feature" | Assertion | **ASSUMPTION** — No user survey or bandwidth analysis |

**Unresolved Questions That Could Invalidate Direction:**
1. **Does ColBERT quality improvement justify 1.7GB + 17s cold start for tldr-swinton's specific use case?** (semantic code search, not general retrieval)
2. **Will existing users actually rebuild indexes?** (History suggests manual migration steps have <30% adoption without aggressive nudging)
3. **Is the plan solving a real user pain or engineering curiosity?** (No cited user complaints about FAISS search quality)

---

## Recommendations

### Must-Fix Before Shipping (Blocks User Success)

1. **Add cold-start feedback:** Progress message during 17s model load.
2. **Show backend in search output:** Users must know which backend answered their query.
3. **Add migration detection:** Nudge existing users to rebuild with `--backend=colbert` after upgrade.
4. **Document install size prominently:** README/AGENTS.md must warn about 1.7GB before user commits.

### Should-Fix Before Shipping (Undermines Value Proposition)

5. **Auto-warm daemon on startup:** Don't make first user query pay the 17s cost.
6. **Add `tldrs semantic warmup` command:** Let users pre-load model explicitly.
7. **Provide quality benchmark data:** Show comparative recall@10 for FAISS vs ColBERT on tldr-bench.
8. **Add `--clean` flag to remove old backend files** when switching.

### Nice-to-Have (Improves Adoption)

9. **Add `tldrs semantic compare` command** for side-by-side A/B testing.
10. **Improve error messages** with actionable recovery steps.
11. **Add backend to MCP tool response metadata** for debugging.

### Pre-Launch Validation (Test Before Promoting to Default)

12. **Run comparative benchmark** on tldr-bench semantic search tasks: FAISS vs ColBERT recall@10.
13. **Measure adoption friction** with 5-10 beta users: install time, rebuild time, quality perception.
14. **Test cold-start UX** in daemon scenario: does 17s feel like a hang or acceptable wait?

---

## Final Assessment

**Ship or Don't Ship?** **SHIP — but only as optional backend, not default, until validation completes.**

**Why:**
- Technical implementation is sound (protocol abstraction, incremental updates).
- Cold-start UX issues are fixable with feedback/pre-warming.
- Migration friction is manageable with nudges and cleanup tools.

**Why Not Default Yet:**
- No evidence quality improvement justifies 1.7GB + 17s cold start for majority of users.
- Existing users have low adoption likelihood without proactive migration UX.
- CI/automation segment will reject this entirely (cold start per invocation).

**Conditions for Promotion to Default:**
1. Benchmark shows ≥15% recall@10 improvement on tldr-bench.
2. Cold-start reduced to ≤5s (via model quantization or lazy-load optimization).
3. Migration tooling added (`tldrs semantic migrate`, auto-cleanup).
4. ≥3 months of optional availability with ≥30% adoption rate among `[semantic-colbert]` installers.

**Smallest Change Set for Meaningful Improvement:**
- Add cold-start spinner + backend indicator in output (fixes 80% of confusion).
- Add migration detection nudge (fixes adoption gap for existing users).
- Document size/latency trade-offs clearly (sets correct expectations).

These three changes would make the feature **usable and discoverable** without delaying shipment for full validation.
