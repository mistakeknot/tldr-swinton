# AGENTS.md Section Size Analysis

## Overview
- **Total file size**: 548 lines
- **Number of sections**: 21 top-level sections
- **Average section size**: 26 lines
- **Median section size**: 13 lines

## Top 5 Largest Sections (by line count)

### 1. Oracle CLI — 125 lines (22.8% of file)
Most comprehensive documentation in the file. Covers:
- Full command reference with all flags
- Authentication workflow
- Browser automation patterns
- Error handling and recovery

**Assessment**: Proportional to tool complexity and frequency of use. No action needed.

### 2. Beads + Agent Mail — 112 lines (20.4% of file)
Second-largest section. Covers:
- Beads database workflow (semantic search, agent memory)
- Agent Mail integration (cross-agent git mailbox)
- Common patterns and troubleshooting

**Assessment**: Reflects two major subsystems. Could split into separate sections if needed, but combined organization is logical.

### 3. Hetzner Cloud CLI (hcloud) — 29 lines (5.3% of file)
Infrastructure CLI reference with commands, flags, and examples.

### 4. Beads Viewer (Graph Intelligence) — 29 lines (5.3% of file)
Visualization tool for Beads knowledge graphs, includes usage patterns.

### 5. ethics-gradient Server — 27 lines (4.9% of file)
Server documentation: services, architecture, diagnostics.

## Size Distribution

| Size Range | Section Count | Examples |
|------------|---------------|----------|
| 100+ lines | 2 sections (9.5%) | Oracle, Beads+AgentMail |
| 25-29 lines | 3 sections (14.3%) | hcloud, BeadsViewer, ethics-gradient |
| 12-16 lines | 4 sections (19.0%) | Superpowers, Autonomous Perms, Moltbot, Project Sync |
| 6-11 lines | 5 sections (23.8%) | Terminal Ref, Earlyoom, Symlinks, git safe.directory, Architecture |
| 1-5 lines | 7 sections (33.3%) | Brief stubs (cc function, Conversation Storage, Unexpected Changes) |

## Key Observations

### 1. **Two Mega-Sections Dominate (43.2% of file)**
   - Oracle (125) + Beads+AgentMail (112) = 237 lines
   - These are the only sections >100 lines
   - Both represent complex, multi-faceted tools/workflows
   - Both justify their size with detailed reference material

### 2. **Top 5 Sections = 49% of Total**
   - Strong concentration in the most frequently referenced tools
   - Reflects actual daily usage patterns

### 3. **Highly Skewed Distribution (Long Tail)**
   - 33% of sections are 6 lines or fewer (stubs/quick refs)
   - Suggests good use of linking to deeper docs (`~/CLAUDE.md`, `workflow-patterns.md`)
   - Avoids redundant duplication across files

### 4. **Sweet Spot: 13-29 Lines (Middle Tier)**
   - 5 sections in the 25-29 range (hcloud, Beads Viewer, ethics-gradient, TLDR-Swinton, Compound Codex)
   - These provide sufficient detail without overwhelming readers
   - Balanced reference material + examples

## Recommendations

### No Action Needed
- Oracle (125 lines) and Beads+AgentMail (112 lines) justify their size via complexity and daily usage
- Section organization is logical and mirrors user workflows

### Consider If Making Changes
1. **For onboarding**: Add a "Quick Start" anchor linking to the 5 largest sections first
2. **For specific lookups**: Ensure table of contents is accurate and searchable
3. **If file exceeds 700 lines**: Consider splitting into domain-specific files (e.g., `AGENTS-tools.md`, `AGENTS-infrastructure.md`)

### Current Health Assessment
- **Structure**: Healthy. Sections are logically grouped.
- **Readability**: Good. Largest sections have clear subsections and examples.
- **Maintainability**: Good. File is under 600 lines, not overwhelming.
- **Format**: Consistent. All sections follow `## Name` convention with clear content below.

## Line Count by Section (Full List)

```
125 ## Oracle CLI
112 ## Beads + Agent Mail
29 ## Hetzner Cloud CLI (hcloud)
29 ## Beads Viewer (Graph Intelligence)
27 ## ethics-gradient Server
25 ## TLDR-Swinton
24 ## Compound Codex Tool Mapping
16 ## POSIX ACLs (critical)
16 ## Cross-Repo Workflows
15 ## QMD (Local Search Engine)
13 ## Troubleshooting
13 ## Superpowers System
13 ## Autonomous Permission Fixing
12 ## Project Sync (mutagen)
11 ## Moltbot
9 ## The cc function (root's .bashrc)
8 ## Terminal Reference
8 ## Earlyoom
7 ## Unexpected Changes Policy
7 ## Conversation Storage Gotcha
7 ## Architecture
6 ## Symlinked dotfiles (/home/claude-user → /root/)
6 ## Git safe.directory
```

**Total**: 548 lines across 23 sections
