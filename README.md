# Local Autonomous AI Aegis

A Git-native, VRAM-efficient, semantic code review and architectural analysis engine. It runs entirely on your local machine, leveraging small (3B-9B) quantization models and CodeGraph knowledge graphs.

## Why Aegis?
Most AI code reviewers suffer from **Framework Blindness** and **Context Starvation**, causing them to hallucinate bugs (e.g., complaining that FastAPI `Depends()` returns `None`). 
Aegis solves this with a **Single-Pass Context Architecture**:
1. **Tree-Sitter Graph:** It parses your codebase into a SQLite graph DB to extract exact caller/callee signatures.
2. **AST Guardrails:** It deterministically analyzes the AST to tag framework-managed safe zones (like Dependency Injection paths or mapped exceptions).
3. **Context Bundling:** It bundles the cross-file edges and the AST guardrails directly into the prompt, resulting in a **0% hallucination rate** even on small 7B parameter models.

## Quick Start

You can run the engine using the included batch wrapper from your repository root:

### 1. Initialize the Storage
Just like `git init`, you need to initialize the aegis storage in your repo.
```bash
.\aegis.bat init
```
This creates the `.aegis/` directory to store content-addressed finding objects.

### 2. Review a File or Symbol
Force the AI to perform a targeted review of a specific function or file.
```bash
.\aegis.bat review --file src/payment/stripe.py --symbol processPayment
```

### 3. Invalidate Cache (2-Hop Decay)
When you modify a symbol, you can trigger a cache invalidation. The engine will mark the symbol and up to 2-hops of its dependents as stale, ensuring the AI re-reviews impacted code without locking up your machine.
```bash
.\aegis.bat invalidate --file src/payment/stripe.py --symbol processPayment
```

### 4. Semantic Merge-Check
Before you merge a PR, run a semantic merge-check. This uses GitNexus MCP to calculate the blast radius of both branches and asks the 9B model to evaluate any overlapping dependencies for logical conflicts.
```bash
.\aegis.bat merge-check --branch-a feature/payment --branch-b feature/tax
```

### 5. Team Sync (Git Notes)
Sync your local AI findings with your team using Git's native infrastructure (requires at least one commit in your repo).
```bash
.\aegis.bat push   # Pushes your local AI findings to origin
.\aegis.bat fetch  # Pulls your team's findings
```

## Environment Configuration
- `ENGINEER_LLM_URL`: The URL to your local OpenAI-compatible inference server (defaults to `http://127.0.0.1:8080/v1`). Set this to point to your local Ollama or llama.cpp instance.
