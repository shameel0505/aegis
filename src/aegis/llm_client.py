import json
import os
import urllib.request
import urllib.error
import subprocess
import sys
from typing import Dict, Any, List
from .schema import FindingDetail

class LLMOrchestrator:
    """
    Natively orchestrates the local inference server (Ollama) as a detached process.
    """
    @staticmethod
    def init_llm(model_id: str = "qwen2.5-coder:7b"):
        print(f"[Aegis Orchestrator] Verifying native LLM dependencies for '{model_id}'...")
        
        # 1. Check if Ollama is installed
        try:
            subprocess.run(["ollama", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[FATAL] Ollama is not installed or not in PATH.")
            print("Please install Ollama manually from https://ollama.com/ to enable local AI execution.")
            sys.exit(1)
            
        # 2. Pull the model
        print(f"[Aegis Orchestrator] Pulling {model_id} into local registry. This may take a while...")
        try:
            subprocess.run(["ollama", "pull", model_id], check=True)
        except subprocess.CalledProcessError:
            print(f"[FATAL] Failed to pull model {model_id} via Ollama.")
            sys.exit(1)
            
        print(f"[Aegis Orchestrator] LLM successfully verified and pulled. Ready for native execution.")

class LocalLLMClient:
    """
    Client to interact with a local llama.cpp server running a 9B model.
    It expects the server to expose an OpenAI-compatible API.
    """
    def __init__(self, base_url: str = None, model_id: str = "qwen2.5-coder:7b"):
        self.base_url = base_url or os.environ.get("AEGIS_LLM_URL", "http://127.0.0.1:11434/v1")
        self.model_id = model_id
        
    def check_health(self) -> bool:
        """Checks if the local LLM server is up and running."""
        try:
            req = urllib.request.Request(f"{self.base_url}/models")
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, Exception):
            return False

    def review_code(self, graph_data: Dict[str, Any]) -> List[FindingDetail]:
        """
        Single-Pass review. Dispatches the file and its Context Bundle to the LLM.
        """
        target_node = graph_data.get("target") or {}
        code_content = target_node.get('code_content', 'No code provided.')
        context_bundle = graph_data.get("context_bundle", [])
        framework = graph_data.get("framework", "generic")
        framework_contract = graph_data.get("framework_contract", "")
        safety_tags = graph_data.get("safety_tags", [])
        
        findings = []
        
        prompt = f"""You are a senior principal engineer performing a rigorous code review. Your goal is to identify DEFECTS, VULNERABILITIES, and ARCHITECTURAL FLAWS.
Do not comment on trivial stylistic issues (e.g. whitespace) unless they severely impact readability.

<CONTEXT>
Target File: {target_node.get('file_path')}
Target Component: {target_node.get('symbol_name')}
</CONTEXT>

<CODE_UNDER_REVIEW>
{code_content}
</CODE_UNDER_REVIEW>

<CONTEXT_BUNDLE>
The graph engine has pre-computed the cross-file connections for this file. 
Use these caller/callee signatures to verify that the code respects external contracts, handles None/null correctly based on how it's called, and doesn't break dependent schemas.
{json.dumps(context_bundle, indent=2)}
</CONTEXT_BUNDLE>

<FRAMEWORK_CONTEXT>
Detected Framework: {framework}
Framework Contracts:
{framework_contract}
</FRAMEWORK_CONTEXT>

<SAFE_REGIONS>
The following regions are tagged as framework-managed or explicitly handled:
{json.dumps(safety_tags, indent=2)}
</SAFE_REGIONS>

<REVIEW_RULES>
1. If uncertain or if no clearly provable issue is found, return an empty findings array.
2. Never hallucinate code that is not present in the <CODE_UNDER_REVIEW> or <CONTEXT_BUNDLE>.
3. Do not flag framework-managed safe regions unless there is direct exploit evidence in the snippet itself.
4. Never recommend weakening authentication/authorization/validation/error-handling behavior.
5. Output MUST be strictly valid JSON without any markdown code blocks or preamble.

<NEGATIVE_CONSTRAINTS>
- Do NOT flag standard framework abstractions, repository patterns, or library methods as vulnerabilities unless you can explicitly prove it. If you lack context, assume the framework handles it safely.
- Do NOT hallucinate type mismatches or broken architectural boundaries. Assume underlying models and serializers handle validation unless proven otherwise.
</NEGATIVE_CONSTRAINTS>
</REVIEW_RULES>

Respond ONLY with a valid JSON object matching this exact schema:
{{
  "findings": [
    {{
      "severity": "WARNING" | "CRITICAL",
      "category": "SECURITY" | "MAINTAINABILITY" | "PERFORMANCE" | "ARCHITECTURE",
      "description": "string (Be highly specific about why it fails)",
      "faulty_snippet": "string (The exact, literal code snippet that is buggy, preserving whitespace)",
      "evidence_graph": [ {{"type": "string", "to": "string"}} ]
    }}
  ]
}}
"""
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": "You are a precise JSON-only code reviewer."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "keep_alive": "5m"
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        
        print(f"    [LLM] Dispatching Single-Pass Context-Aware Review...")
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    start = content.find("{")
                    end = content.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        parsed = json.loads(content[start:end + 1])
                    else:
                        raise
                
                raw_findings = parsed.get("findings", [])
                for f in raw_findings:
                    if f.get("severity") in ["WARNING", "CRITICAL"] and f.get("faulty_snippet"):
                        findings.append(FindingDetail(
                            severity=f.get("severity"),
                            category=f.get("category", "ARCHITECTURE"),
                            description=f.get("description", "No description."),
                            faulty_snippet=f.get("faulty_snippet"),
                            evidence_graph=f.get("evidence_graph", [])
                        ))
        except Exception as e:
            print(f"    [LLM] Error during review: {e}")
            
        return findings
