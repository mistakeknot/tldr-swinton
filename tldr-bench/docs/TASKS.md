# Task Definitions

Tasks are defined as YAML lists. Required fields:
- id
- title
- repo
- entry
- expected_files
- expected_lines
- type
- notes

## Built-in task files

- curated
- public

## Example

```yaml
- id: cur-001
  title: "Trim docstring noise in embeddings"
  repo: "tldr-swinton"
  entry: "tldr_swinton/index.py:_clean_doc"
  expected_files: ["src/tldr_swinton/index.py"]
  expected_lines: [204, 218, 228]
  type: "small_refactor"
  notes: "Docstring truncation path used by embed text builder."
```
