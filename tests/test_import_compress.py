from tldr_swinton.modules.core.import_compress import (
    ImportFrequencyIndex,
    compress_imports_section,
    format_common_imports,
)


def test_frequency_index_build() -> None:
    file_imports = {
        "a.py": ["import os", "from typing import Optional"],
        "b.py": ["import os", "from typing import List"],
        "c.py": ["import os"],
    }

    index = ImportFrequencyIndex.build(file_imports)

    assert index.total_files == 3
    assert index.frequencies[("os", "")] == 3
    assert index.frequencies[("typing", "Optional")] == 1
    assert index.frequencies[("typing", "List")] == 1


def test_ubiquitous_detection_50pct() -> None:
    file_imports = {
        "a.py": ["import os", "from pathlib import Path"],
        "b.py": ["import os", "from pathlib import Path"],
        "c.py": ["import os", "from typing import Optional"],
    }

    index = ImportFrequencyIndex.build(file_imports)
    ubiquitous = index.get_ubiquitous(threshold=0.5)

    assert ubiquitous == {"import os", "from pathlib import Path"}


def test_ubiquitous_detection_custom_threshold() -> None:
    file_imports = {
        "a.py": ["import os", "from pathlib import Path"],
        "b.py": ["import os", "from pathlib import Path"],
        "c.py": ["import os", "from typing import Optional"],
    }

    index = ImportFrequencyIndex.build(file_imports)
    ubiquitous = index.get_ubiquitous(threshold=0.3)

    assert ubiquitous == {
        "import os",
        "from pathlib import Path",
        "from typing import Optional",
    }


def test_unique_imports_extraction() -> None:
    file_imports = {
        "a.py": ["import os", "from typing import Optional"],
        "b.py": ["import os", "from typing import List"],
        "c.py": ["import os"],
    }

    index = ImportFrequencyIndex.build(file_imports)

    assert index.get_unique_imports("a.py", file_imports["a.py"]) == [
        "from typing import Optional"
    ]
    assert index.get_unique_imports("b.py", file_imports["b.py"]) == [
        "from typing import List"
    ]
    assert index.get_unique_imports("c.py", file_imports["c.py"]) == []


def test_format_common_imports() -> None:
    common = {
        "from typing import Optional",
        "from typing import List",
        "from pathlib import Path",
        "import json",
        "import os",
    }

    out = format_common_imports(common)

    assert out == "json, os, pathlib: Path, typing: {List, Optional}"


def test_compress_roundtrip() -> None:
    file_imports = {
        "a.py": ["import os", "from typing import Optional", "from pathlib import Path"],
        "b.py": ["import os", "from pathlib import Path", "from typing import List"],
        "c.py": ["import os"],
    }

    common_header, per_file = compress_imports_section(file_imports, threshold=0.5)

    assert common_header.startswith("## Common Imports")
    assert set(per_file) == set(file_imports)

    index = ImportFrequencyIndex.build(file_imports)
    common = index.get_ubiquitous(threshold=0.5)

    for file_path, imports in file_imports.items():
        unique = index.get_unique_imports(file_path, imports)
        original = ImportFrequencyIndex.build({"only.py": imports}).get_ubiquitous(threshold=0.0)
        reconstructed = set(unique) | (common & original)
        assert reconstructed == original


def test_empty_imports() -> None:
    file_imports = {
        "a.py": [],
        "b.py": [],
    }

    index = ImportFrequencyIndex.build(file_imports)
    common_header, per_file = compress_imports_section(file_imports)

    assert index.total_files == 2
    assert index.frequencies == {}
    assert index.get_ubiquitous() == set()
    assert common_header == ""
    assert per_file == {"a.py": "", "b.py": ""}
