# Harness-Aware Installation Repair Implementation Plan

> **For Codex:** Execute this plan sequentially in the current session. The tasks share installer, plugin, and guidance state.

**Goal:** Make `tldrs` reliably executable from non-interactive agent shells and update its integrations to use modern harness isolation and large-context models without unconditional reconnaissance overhead.

**Architecture:** Keep the project virtual environment as the single runtime and install small user-bin launchers that `exec` its entry points without changing the caller's working directory. Replace unconditional session/read interception with adaptive CLI, MCP, and forked-skill guidance; keep hooks limited to health checks and background preparation. Document the capability assumptions and verification date rather than hard-coding model names into routing logic.

**Tech Stack:** Bash, Python/pytest, Claude Code plugin hooks and skills, Codex Agent Skills, Markdown.

## Must-Haves

**Truths**
- `tldrs` launched from an arbitrary repository keeps that repository as its working directory.
- A stale or import-broken executable is reported as unusable rather than merely "installed."
- Claude reconnaissance runs in an isolated Explore context only for large, unfamiliar, noisy, or multi-file work.
- Codex guidance treats TLDR as adaptive reconnaissance, not a mandatory pre-read ritual.
- Current harness/model assumptions are dated and linked to primary documentation.

**Artifacts**
- `scripts/install-launchers.sh` creates stable `tldrs`, `tldr-swinton`, and `tldr-mcp` launchers.
- `scripts/install.sh` installs and verifies the launchers without swallowing dependency failures.
- `tests/test_install_script.py` covers launcher behavior and installer contracts.
- `tests/test_harness_guidance.py` covers the plugin/skill routing contracts.
- `docs/harness-capabilities.md` records the current integration rationale.

**Key Links**
- `scripts/install.sh` calls `scripts/install-launchers.sh` after `uv sync` creates `.venv/bin/*`.
- The Claude skill uses `context: fork` with `agent: Explore`; plugin hooks do not duplicate file content already read by the model.
- `docs/QUICKSTART.md`, `docs/agent-workflow.md`, README, and both harness skills share the same adaptive decision boundary.

### Task 1: Reproduce and lock down launcher behavior

**Files:**
- Create: `scripts/install-launchers.sh`
- Modify: `scripts/install.sh`
- Modify: `scripts/uninstall.sh`
- Modify: `tests/test_install_script.py`

1. Add failing tests that execute generated launchers from a different working directory and assert that CWD and arguments are preserved.
2. Add failing assertions that dependency installation errors are not swallowed and interactive aliases are not created.
3. Run `pytest tests/test_install_script.py -v` and confirm the new tests fail for missing behavior.
4. Implement the launcher generator and wire it into install/uninstall.
5. Re-run the targeted tests and commit the installation repair.

<verify>
- run: `uv run pytest tests/test_install_script.py -v`
  expect: exit 0
</verify>

### Task 2: Make harness integration adaptive

**Files:**
- Modify: `.claude-plugin/skills/tldrs-session-start/SKILL.md`
- Modify: `.codex/skills/tldrs-agent-workflow/SKILL.md`
- Modify: `.claude-plugin/hooks/hooks.json`
- Modify: `.claude-plugin/hooks/setup.sh`
- Delete: `.claude-plugin/hooks/post-read-extract.sh`
- Create: `tests/test_harness_guidance.py`

1. Add failing tests for an Explore-forked Claude skill, adaptive Codex wording, executable health checks, and absence of automatic post-read duplication.
2. Run `pytest tests/test_harness_guidance.py -v` and confirm the tests fail for the existing unconditional behavior.
3. Narrow skill triggers to large/unfamiliar, multi-file, diff-heavy, or delegation-heavy tasks.
4. Move Claude reconnaissance into a forked Explore context and remove the post-read duplication hook.
5. Reduce the Setup hook to executable health checks plus quiet background prebuild.
6. Re-run the targeted tests and commit the harness integration update.

<verify>
- run: `uv run pytest tests/test_harness_guidance.py -v`
  expect: exit 0
</verify>

### Task 3: Update capability guidance

**Files:**
- Create: `docs/harness-capabilities.md`
- Modify: `docs/QUICKSTART.md`
- Modify: `docs/agent-workflow.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

1. Document the July 2026 primary-source capability baseline for Claude Code, Codex, Agent Skills, MCP, and 1M-class models.
2. Explain why large context does not remove retrieval needs but does change when forced retrieval is worthwhile.
3. Update quickstart and integration docs to the adaptive decision boundary and accurate plugin surface.
4. Run documentation/contract tests and commit the documentation update.

<verify>
- run: `uv run pytest tests/test_harness_guidance.py tests/test_install_script.py -v`
  expect: exit 0
</verify>

### Task 4: Repair the live installation and verify end to end

**Files:**
- No source files beyond Tasks 1-3.

1. Sync the project environment with test dependencies.
2. Remove only the confirmed stale Homebrew Python 3.11 editable installation whose target no longer exists.
3. Install the new launchers from this checkout.
4. Run the repository's exact CI command, focused installation/harness tests, manifest/version checks, and live commands from `/Users/sma/projects`. (The checkout contains separately configured root, structural, evaluation, and `tldr-bench` suites, so bare recursive pytest collection is not a valid aggregate command.)
5. Review the diff, update and close Beads issue `mk-4e4q`, pull/rebase, push Beads and Git, and confirm `main` is up to date.

<verify>
- run: `tldrs --version`
  expect: contains "0.7.19"
- run: `tldrs structure /Users/sma/projects/tldr-swinton/src/tldr_swinton`
  expect: exit 0
- run: `PYTHONPATH=tldr-bench uv run python -m pytest tldr-bench/tests/test_compare_results_cli.py tldr-bench/tests/test_cassette_variant.py -q`
  expect: exit 0
- run: `uv run python -m pytest tests/test_install_script.py tests/test_harness_guidance.py tests/test_capability_guidance.py -q`
  expect: exit 0
</verify>
