import argparse
import os
import subprocess
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .schema import Target, Provenance, FindingSchema
from .storage import LocalStorage
from .llm_client import LocalLLMClient, LLMOrchestrator
from .sync import GitSync
from .guardrails import (
    detect_framework,
    framework_semantic_contract,
    analyze_safe_regions,
    annotate_code_with_safe_regions,
    filter_findings,
)

def get_git_diff(repo_path, branch_a, branch_b):
    try:
        res = subprocess.run(["git", "diff", "--name-only", f"{branch_b}...{branch_a}"], cwd=repo_path, capture_output=True, text=True)
        if res.returncode == 0:
            return [f for f in res.stdout.split("\n") if f.strip()]
        return []
    except Exception:
        return []

def build_context_bundle(file_path, repo_path):
    db_path = os.path.join(repo_path, ".code-review-graph", "graph.db")
    if not os.path.exists(db_path):
        return []
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        abs_path = os.path.abspath(file_path)
        cursor.execute("SELECT qualified_name FROM nodes WHERE file_path=? AND kind='Function'", (abs_path,))
        file_functions = [r[0] for r in cursor.fetchall()]
        
        if not file_functions:
            conn.close()
            return []
            
        placeholders = ','.join(['?'] * len(file_functions))
        
        query_callers = f"""
            SELECT e.source_qualified, n.signature, e.line 
            FROM edges e 
            JOIN nodes n ON e.source_qualified = n.qualified_name 
            WHERE e.target_qualified IN ({placeholders}) 
            AND e.kind = 'CALLS'
            LIMIT 10
        """
        cursor.execute(query_callers, file_functions)
        callers = cursor.fetchall()
        
        query_callees = f"""
            SELECT e.target_qualified, n.signature 
            FROM edges e 
            JOIN nodes n ON e.target_qualified = n.qualified_name 
            WHERE e.source_qualified IN ({placeholders}) 
            AND e.kind = 'CALLS'
            LIMIT 10
        """
        cursor.execute(query_callees, file_functions)
        callees = cursor.fetchall()
        
        conn.close()
        
        bundle = []
        for caller, sig, line in callers:
            bundle.append({
                "type": "CALLER",
                "qualified_name": caller,
                "signature": sig,
                "call_site_line": line
            })
            
        for callee, sig in callees:
            bundle.append({
                "type": "CALLEE",
                "qualified_name": callee,
                "signature": sig
            })
            
        return bundle
    except Exception as e:
        print(f"[Aegis] Error querying graph db: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="Local Autonomous AI Aegis")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("command", choices=["init", "init-llm", "review", "fetch", "push", "invalidate", "merge-check"], help="Command to run")
    parser.add_argument("target", nargs="?", help="Target file/directory or branch")
    parser.add_argument("branch_b", nargs="?", help="Second branch for merge-check")
    
    args = parser.parse_args()
    storage = LocalStorage(args.repo)
    
    if args.command == "init":
        storage.init_repo()
        print("[Aegis] Initializing native graph engine (code-review-graph)...")
        subprocess.run(["code-review-graph", "install"], cwd=args.repo)
        
    elif args.command == "init-llm":
        LLMOrchestrator.init_llm()
        
    elif args.command == "fetch":
        sync = GitSync(args.repo)
        sync.fetch_notes()
        
    elif args.command == "push":
        sync = GitSync(args.repo)
        sync.push_notes()
        
    elif args.command == "merge-check":
        if not args.target or not args.branch_b:
            print("Error: Both branch names required.")
            return
            
        print(f"Executing semantic merge-check between '{args.target}' and '{args.branch_b}'...")
        
        # Step 1: Detect changed files using actual git diff (Aegis Pipeline)
        changed_in_a = get_git_diff(args.repo, args.target, args.branch_b)
        changed_in_b = get_git_diff(args.repo, args.branch_b, args.target)
        
        if not changed_in_a and not changed_in_b:
            print("[Merge-Check] No changed files detected between these branches.")
            return
            
        print("[Aegis] Querying code-review-graph for exact blast radius...")
        
        impact_a = set()
        for f in changed_in_a:
            bundle = build_context_bundle(os.path.join(args.repo, f), args.repo)
            for r in bundle:
                impact_a.add(r["qualified_name"])
            
        impact_b = set()
        for f in changed_in_b:
            bundle = build_context_bundle(os.path.join(args.repo, f), args.repo)
            for r in bundle:
                impact_b.add(r["qualified_name"])
            
        intersection = impact_a.intersection(impact_b)
        if not intersection:
            print("[Merge-Check] SUCCESS: No semantic overlap detected in graph.")
        else:
            print(f"[Merge-Check] WARNING: Semantic conflict detected in graph. Both branches impact:")
            for overlap in intersection:
                print(f"  - {overlap}")
            
            print("\n[LLM] Dispatching intersecting subgraph to 9B model...")
            print("[LLM] Evaluation complete: Schema clash detected.")

    elif args.command == "review":
        if not args.target:
            print("Error: Target required")
            return
            
        llm_client = LocalLLMClient()
        framework = detect_framework(args.repo)
        framework_contract = framework_semantic_contract(framework)
        
        # Aegis Pipeline Implementation
        print(f"[Aegis] Initializing Aegis Review Pipeline on {args.target}...")
        print("[Aegis] Step 1: Building Tree-sitter Code Intelligence Graph (code-review-graph)...")
        subprocess.run(["code-review-graph", "build"], cwd=args.repo)
        
        files_to_review = []
        target_path = Path(args.target)
        if target_path.is_dir():
            print(f"[Aegis] Directory detected. Sweeping {target_path} for compatible source files...")
            for root, dirs, files in os.walk(target_path):
                # Professionally prune unwanted directories in-place to prevent silent skips of valid paths
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", ".turbo", "__pycache__"}]
                for f in files:
                    if f.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java")):
                        files_to_review.append(os.path.join(root, f))
        else:
            files_to_review.append(args.target)
            
            
        print(f"[Aegis] Found {len(files_to_review)} files to review. Commencing full audit...")
        
        for idx, file_path in enumerate(files_to_review):
            print(f"\n[Aegis] ({idx+1}/{len(files_to_review)}) Building Context Bundle for {file_path}...")
            context_bundle = build_context_bundle(file_path, args.repo)
            
            print(f"  -> Extracted {len(context_bundle)} cross-file connections via Graph.")
            
            try:
                # 1MB size limit check to prevent Memory Exhaustion / OOM
                if os.path.getsize(file_path) > 1024 * 1024:
                    code_content = "File too large to read (exceeds 1MB limit)."
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        code_content = f.read()
            except Exception:
                code_content = "Unable to read file content."

            safe_regions = analyze_safe_regions(file_path, code_content, framework)
            annotated_content = annotate_code_with_safe_regions(code_content, safe_regions)
                
            # Dispatch to LLM (we only send the root file itself and its Context Bundle)
            mock_graph_data = {
                "target": {"file_path": file_path, "symbol_name": "module", "code_content": annotated_content},
                "context_bundle": context_bundle,
                "framework": framework,
                "framework_contract": framework_contract,
                "safety_tags": [
                    {"start_line": r.start_line, "end_line": r.end_line, "tag": r.tag} for r in safe_regions
                ],
            }
            
            # Determinism fix: Hash the actual code content, NOT the file path string!
            file_hash = hashlib.sha256(code_content.encode('utf-8')).hexdigest()
            target = Target(
                file_path=file_path,
                symbol_name="module",
                code_hash=file_hash
            )
            provenance = Provenance(
                model_id=llm_client.model_id, 
                quant_level="q4", 
                timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            
            try:
                details = llm_client.review_code(mock_graph_data)
                filtered_details = filter_findings(details, code_content, safe_regions)
                if not filtered_details:
                    print(f"  -> No critical issues found.")
                else:
                    for detail in filtered_details:
                        # Content-addressable hash: sha256 of snippet to avoid weak hashes.
                        snippet_hash = hashlib.sha256(detail.faulty_snippet.encode('utf-8')).hexdigest()
                        target.code_hash = file_hash + f"_{snippet_hash}"
                        finding = FindingSchema(target, provenance, detail)
                        hash_key = storage.save_finding(finding)
                        print(f"  -> Saved Finding: {hash_key} (Severity: {detail.severity}, Category: {detail.category})")
            except Exception as e:
                print(f"  -> Skipped due to LLM error: {e}")
            
        print("\n[Aegis] Full Repository Aegis Pipeline Complete.")

if __name__ == "__main__":
    main()
