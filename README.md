# Aegis: Autonomous Local AI Code Review Engine

[![Build Status](https://img.shields.io/github/actions/workflow/status/shameel0505/aegis/release.yml?branch=master)](https://github.com/shameel0505/aegis/actions)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](https://github.com/shameel0505/aegis)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Git-native, VRAM-efficient, semantic code review and architectural analysis engine. It runs entirely on your local machine, leveraging small (3B-9B) quantization models and CodeGraph knowledge graphs to prevent cloud data leaks.

## Why Aegis?
Most AI code reviewers suffer from **Framework Blindness** and **Context Starvation**, causing them to hallucinate bugs (e.g., complaining that FastAPI `Depends()` returns `None`). 
Aegis solves this with a **Single-Pass Context Architecture**:

1. **Tree-Sitter Graph:** It parses your codebase into a SQLite graph DB to extract exact caller/callee signatures.
2. **AST Guardrails:** It deterministically analyzes the AST to tag framework-managed safe zones (like Dependency Injection paths or mapped exceptions).
3. **Context Bundling:** It bundles the cross-file edges and the AST guardrails directly into the prompt, resulting in a **drastically reduced hallucination rate** even on small 7B parameter models.

```mermaid
flowchart LR
    A[Source Code] -->|AST Parsing| B(Guardrails Filter)
    A -->|Tree-Sitter| C[(SQLite Graph DB)]
    C -->|Caller/Callee Signatures| D[Context Bundle]
    B -->|Safe Zones Annotated| D
    D -->|Strict JSON Schema| E[Local LLM (Qwen 7B)]
    E --> F{Findings JSON}
    F -->|Stored in .aegis/objects| G[Git Notes Sync]
```

## Quick Start

You can run the engine using the compiled executable from your repository root:

### 1. Initialize the Storage
Just like `git init`, you need to initialize the aegis storage in your repo.
```bash
dist\aegis.exe init
```
This creates the `.aegis/` directory to store content-addressed finding objects.

### 2. Review a File or Symbol
Force the AI to perform a targeted review of a specific function, file, or full directory.
```bash
dist\aegis.exe review --file src/payment/stripe.py
dist\aegis.exe review .  # Sweeps entire repository
```

### 3. Invalidate Cache (2-Hop Decay)
When you modify a symbol, you can trigger a cache invalidation. The engine will mark the symbol and up to 2-hops of its dependents as stale, ensuring the AI re-reviews impacted code without locking up your machine.
```bash
dist\aegis.exe invalidate --file src/payment/stripe.py --symbol processPayment
```

### 4. Semantic Merge-Check
Before you merge a PR, run a semantic merge-check. This uses Git to calculate the blast radius of both branches and asks the model to evaluate any overlapping dependencies for logical conflicts.
```bash
dist\aegis.exe merge-check --branch-a feature/payment --branch-b feature/tax
```

### 5. Team Sync (Git Notes)
Sync your local AI findings with your team using Git's native infrastructure (requires at least one commit in your repo).
```bash
dist\aegis.exe push   # Pushes your local AI findings to origin
dist\aegis.exe fetch  # Pulls your team's findings
```

## Local Development & Compilation

Aegis is intentionally built using **100% Python Standard Library** modules (Zero `pip` dependencies!), meaning you never have to deal with broken virtual environments.

To compile the `aegis.exe` standalone binary for yourself:
1. Ensure `pyinstaller` is installed (`pip install pyinstaller`).
2. Run the provided build script:
```powershell
.\build.ps1
```

## Environment Configuration
- `ENGINEER_LLM_URL`: The URL to your local OpenAI-compatible inference server (defaults to `http://127.0.0.1:8080/v1`). Set this to point to your local Ollama or llama.cpp instance.
