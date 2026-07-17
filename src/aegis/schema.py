import hashlib
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

@dataclass
class Target:
    file_path: str
    symbol_name: str
    code_hash: str

@dataclass
class Provenance:
    model_id: str
    quant_level: str
    timestamp: str

@dataclass
class FindingDetail:
    severity: str
    category: str
    description: str
    faulty_snippet: str
    evidence_graph: List[Dict[str, str]]

class FindingSchema:
    def __init__(self, target: Target, provenance: Provenance, finding: FindingDetail, schema_version: str = "1.1"):
        self.schema_version = schema_version
        self.target = target
        self.provenance = provenance
        self.finding = finding
        self.hash_key = self._generate_hash()

    def _generate_hash(self) -> str:
        # Deterministic hash: sha256(code_hash + model_id + quant_level)
        raw_string = f"{self.target.code_hash}:{self.provenance.model_id}:{self.provenance.quant_level}"
        return hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "hash_key": self.hash_key,
            "target": asdict(self.target),
            "provenance": asdict(self.provenance),
            "finding": asdict(self.finding)
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

if __name__ == "__main__":
    # Test deterministic hashing
    target = Target(file_path="src/auth/login.ts", symbol_name="authenticateUser", code_hash="7d8a9b")
    provenance = Provenance(model_id="qwen2.5-coder-3b", quant_level="q4_k_m", timestamp="2026-07-15T10:00:00Z")
    detail = FindingDetail(
        severity="CRITICAL",
        category="SECURITY_SQL_INJECTION",
        description="Unsanitized input flows directly into the database driver.",
        faulty_snippet="db.execute(user_input)",
        evidence_graph=[
            {"type": "DATA_FLOW", "from": "api/route.ts:L45", "to": "src/auth/login.ts:L12"}
        ]
    )
    
    finding1 = FindingSchema(target, provenance, detail)
    
    # Prove that generating it again at a different time but with same code/model yields same hash
    provenance2 = Provenance(model_id="qwen2.5-coder-3b", quant_level="q4_k_m", timestamp="2026-07-15T11:00:00Z")
    finding2 = FindingSchema(target, provenance2, detail)
    
    print(f"Finding 1 Hash: {finding1.hash_key}")
    print(f"Finding 2 Hash: {finding2.hash_key}")
    print(f"Deterministic Match: {finding1.hash_key == finding2.hash_key}")
