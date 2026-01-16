from __future__ import annotations

from pathlib import Path

from .hybrid_extractor import HybridExtractor


class SymbolInfo:
    def __init__(
        self,
        signature: str,
        file: str,
        lines: tuple[int, int] | None,
    ) -> None:
        self.signature = signature
        self.file = file
        self.lines = lines


class SymbolRegistry:
    def __init__(self, root: str | Path, language: str = "python") -> None:
        self.root = Path(root)
        self.language = language

    def get(self, symbol_id: str) -> SymbolInfo:
        if ":" not in symbol_id:
            raise KeyError(symbol_id)
        file_part, name = symbol_id.split(":", 1)
        file_path = self.root / file_part
        extractor = HybridExtractor()
        info = extractor.extract(str(file_path))
        for func in info.functions:
            if func.name == name:
                line = func.line_number or 0
                return SymbolInfo(func.signature(), file_part, (line, line))
        raise KeyError(symbol_id)
