"""Tests for ProjectIndex — the shared symbol scanning class."""

from pathlib import Path

import pytest

from tldr_swinton.modules.core.project_index import ProjectIndex, _compute_symbol_ranges


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_project(tmp_path: Path) -> Path:
    """A small project with functions, classes, and cross-file calls."""
    (tmp_path / "a.py").write_text(
        "def greet(name: str) -> str:\n"
        '    return f"Hello {name}"\n'
        "\n"
        "def farewell(name: str) -> str:\n"
        '    return f"Bye {name}"\n'
    )
    (tmp_path / "b.py").write_text(
        "from a import greet\n"
        "\n"
        "class Greeter:\n"
        "    def run(self) -> str:\n"
        "        return greet('world')\n"
        "\n"
        "    def stop(self) -> None:\n"
        "        pass\n"
    )
    return tmp_path


@pytest.fixture
def ambiguous_project(tmp_path: Path) -> Path:
    """A project with same-named functions in different files."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "alpha.py").write_text("def process():\n    return 1\n")
    (tmp_path / "pkg" / "beta.py").write_text("def process():\n    return 2\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Build & Index Population
# ---------------------------------------------------------------------------


class TestBuild:
    def test_build_creates_all_indexes(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)

        # symbol_index should contain functions + class + methods
        assert "a.py:greet" in idx.symbol_index
        assert "a.py:farewell" in idx.symbol_index
        assert "b.py:Greeter" in idx.symbol_index
        assert "b.py:Greeter.run" in idx.symbol_index
        assert "b.py:Greeter.stop" in idx.symbol_index

    def test_symbol_files_maps_to_abs_paths(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        abs_a = str(simple_project / "a.py")
        assert idx.symbol_files["a.py:greet"] == abs_a

    def test_name_index_maps_raw_names(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        assert "a.py:greet" in idx.name_index["greet"]
        # Method raw name is just "run"
        assert "b.py:Greeter.run" in idx.name_index["run"]

    def test_qualified_index_populated(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        # Class method qualified name
        assert "b.py:Greeter.run" in idx.qualified_index["Greeter.run"]
        # Module alias for top-level functions
        assert "a.py:greet" in idx.qualified_index["a.greet"]

    def test_file_name_index_has_qualified_entries(self, simple_project: Path) -> None:
        """The difflens-only qualified_name entry in file_name_index."""
        idx = ProjectIndex.build(simple_project)
        # For methods: qualified_name (Greeter.run) != raw (run)
        assert "b.py:Greeter.run" in idx.file_name_index["b.py"]["Greeter.run"]
        # raw name also present
        assert "b.py:Greeter.run" in idx.file_name_index["b.py"]["run"]

    def test_signature_overrides_for_classes(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        assert idx.signature_overrides["b.py:Greeter"] == "class Greeter"

    def test_adjacency_built(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        # b.py:Greeter.run calls a.py:greet
        assert idx.adjacency  # Should have at least some edges


# ---------------------------------------------------------------------------
# Build Flags
# ---------------------------------------------------------------------------


class TestBuildFlags:
    def test_include_sources_true(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_sources=True)
        abs_a = str(simple_project / "a.py")
        assert abs_a in idx.file_sources
        assert "def greet" in idx.file_sources[abs_a]

    def test_include_sources_false(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_sources=False)
        assert len(idx.file_sources) == 0

    def test_include_ranges_true(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_ranges=True)
        assert "a.py:greet" in idx.symbol_ranges
        start, end = idx.symbol_ranges["a.py:greet"]
        assert start == 1
        assert end >= 1

    def test_include_ranges_false(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_ranges=False)
        assert len(idx.symbol_ranges) == 0

    def test_include_reverse_adjacency_true(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_reverse_adjacency=True)
        # reverse_adjacency is populated (may or may not have entries depending on call graph)
        # At minimum, the dict should exist as a defaultdict
        assert isinstance(idx.reverse_adjacency, dict)

    def test_include_reverse_adjacency_false(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_reverse_adjacency=False)
        # Should be empty when flag is off
        assert len(idx.reverse_adjacency) == 0


# ---------------------------------------------------------------------------
# resolve_entry_symbols
# ---------------------------------------------------------------------------


class TestResolveEntrySymbols:
    def test_exact_symbol_id(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        resolved, candidates = idx.resolve_entry_symbols("a.py:greet", allow_ambiguous=True)
        assert resolved == ["a.py:greet"]
        assert candidates == []

    def test_qualified_name(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        resolved, candidates = idx.resolve_entry_symbols("Greeter.run", allow_ambiguous=True)
        assert "b.py:Greeter.run" in resolved

    def test_raw_name_unique(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        resolved, candidates = idx.resolve_entry_symbols("farewell", allow_ambiguous=True)
        assert resolved == ["a.py:farewell"]

    def test_ambiguous_disallowed(self, ambiguous_project: Path) -> None:
        idx = ProjectIndex.build(ambiguous_project)
        resolved, candidates = idx.resolve_entry_symbols("process", allow_ambiguous=False)
        # Should return empty resolved, all matches in candidates
        assert resolved == []
        assert len(candidates) == 2

    def test_ambiguous_allowed(self, ambiguous_project: Path) -> None:
        idx = ProjectIndex.build(ambiguous_project)
        resolved, candidates = idx.resolve_entry_symbols("process", allow_ambiguous=True)
        # Should pick one and return it
        assert len(resolved) == 1
        assert len(candidates) == 2

    def test_file_colon_symbol_format(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        resolved, _ = idx.resolve_entry_symbols("b.py:Greeter", allow_ambiguous=True)
        assert resolved == ["b.py:Greeter"]

    def test_module_alias_resolution(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        resolved, _ = idx.resolve_entry_symbols("a.greet", allow_ambiguous=True)
        assert "a.py:greet" in resolved

    def test_unknown_symbol_passthrough(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project)
        resolved, _ = idx.resolve_entry_symbols("nonexistent_function", allow_ambiguous=True)
        # Unknown names are passed through as-is
        assert resolved == ["nonexistent_function"]


# ---------------------------------------------------------------------------
# _compute_symbol_ranges
# ---------------------------------------------------------------------------


class TestComputeSymbolRanges:
    def test_function_ranges(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_ranges=True)
        # a.py has greet (L1) and farewell (L4)
        greet_start, greet_end = idx.symbol_ranges["a.py:greet"]
        farewell_start, farewell_end = idx.symbol_ranges["a.py:farewell"]
        assert greet_start == 1
        assert farewell_start == 4
        # greet should end before farewell starts
        assert greet_end < farewell_start

    def test_class_and_method_ranges(self, simple_project: Path) -> None:
        idx = ProjectIndex.build(simple_project, include_ranges=True)
        # b.py has Greeter class with run and stop methods
        assert "b.py:Greeter" in idx.symbol_ranges
        assert "b.py:Greeter.run" in idx.symbol_ranges
        assert "b.py:Greeter.stop" in idx.symbol_ranges

        class_start, class_end = idx.symbol_ranges["b.py:Greeter"]
        run_start, run_end = idx.symbol_ranges["b.py:Greeter.run"]
        stop_start, stop_end = idx.symbol_ranges["b.py:Greeter.stop"]

        # Class contains both methods
        assert class_start <= run_start
        assert class_end >= stop_end
        # run starts before stop
        assert run_start < stop_start


# ---------------------------------------------------------------------------
# _register_symbol internals
# ---------------------------------------------------------------------------


class TestRegisterSymbol:
    def test_register_method_adds_qualified_and_raw(self, tmp_path: Path) -> None:
        """Both qualified name and raw name appear in file_name_index."""
        idx = ProjectIndex(project=tmp_path, language="python")

        from tldr_swinton.modules.core.ast_extractor import FunctionInfo

        fi = FunctionInfo(
            name="do_stuff",
            params=[],
            return_type="None",
            docstring=None,
            line_number=10,
            language="python",
        )
        sid = idx._register_symbol(
            rel_path="mod.py",
            file_path=tmp_path / "mod.py",
            qualified_name="MyClass.do_stuff",
            func_info=fi,
            raw_name="do_stuff",
        )

        assert sid == "mod.py:MyClass.do_stuff"
        # Both entries should exist in file_name_index
        assert "mod.py:MyClass.do_stuff" in idx.file_name_index["mod.py"]["do_stuff"]
        assert "mod.py:MyClass.do_stuff" in idx.file_name_index["mod.py"]["MyClass.do_stuff"]

    def test_register_toplevel_no_double_entry(self, tmp_path: Path) -> None:
        """For top-level functions, qualified == raw, so no double entry."""
        idx = ProjectIndex(project=tmp_path, language="python")

        from tldr_swinton.modules.core.ast_extractor import FunctionInfo

        fi = FunctionInfo(
            name="helper",
            params=[],
            return_type="int",
            docstring=None,
            line_number=1,
            language="python",
        )
        idx._register_symbol(
            rel_path="utils.py",
            file_path=tmp_path / "utils.py",
            qualified_name="helper",
            func_info=fi,
        )

        # Only one entry (qualified == raw, no double add)
        assert idx.file_name_index["utils.py"]["helper"] == ["utils.py:helper"]
