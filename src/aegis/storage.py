import os
import json
from pathlib import Path
from .schema import FindingSchema

class LocalStorage:
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.engineer_dir = self.repo_path / ".aegis"
        self.objects_dir = self.engineer_dir / "objects"
        self.refs_dir = self.engineer_dir / "refs" / "heads"
        self.notes_dir = self.engineer_dir / "notes"
        
    def init_repo(self):
        """Initialize the .aegis directory structure, similar to .git"""
        created = not self.engineer_dir.exists()
        self.engineer_dir.mkdir(parents=True, exist_ok=True)
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.refs_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        if created:
            print(f"Initialized empty engineer repository in {self.engineer_dir}")
            
    def _get_object_path(self, hash_key: str) -> Path:
        """Returns the sharded path for an object, e.g., objects/fa/3fb32d..."""
        if len(hash_key) < 3:
            raise ValueError("Hash key too short for sharding.")
        prefix = hash_key[:2]
        filename = hash_key[2:]
        dir_path = self.objects_dir / prefix
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / filename

    def save_finding(self, finding: FindingSchema) -> str:
        """
        Saves the finding as a JSON object, keyed by its content hash.
        If it already exists, we have a cache hit.
        """
        if not self.engineer_dir.exists():
            print("Error: Aegis repository not initialized. Run 'aegis init' first.")
            return ""
            
        obj_file = self._get_object_path(finding.hash_key)
        
        # If it already exists, it's a cache hit. No need to rewrite.
        if obj_file.exists():
            print(f"Cache hit for finding {finding.hash_key}")
            return finding.hash_key
            
        tmp_file = obj_file.with_suffix(".tmp")
        with open(tmp_file, 'w', encoding='utf-8') as f:
            f.write(finding.to_json())
        os.replace(tmp_file, obj_file)
            
        print(f"Saved new finding {finding.hash_key}")
        return finding.hash_key

    def get_finding(self, hash_key: str) -> dict:
        obj_file = self._get_object_path(hash_key)
        
        if not obj_file.exists():
            raise FileNotFoundError(f"Finding object {hash_key} not found.")
            
        with open(obj_file, 'r', encoding='utf-8') as f:
            return json.loads(f.read())

if __name__ == "__main__":
    from .schema import Target, Provenance, FindingDetail
    
    storage = LocalStorage(".")
    storage.init_repo()
    
    target = Target(file_path="src/main.py", symbol_name="main", code_hash="abc1234")
    provenance = Provenance(model_id="qwen-3b", quant_level="q4", timestamp="2026-07-15T12:00:00Z")
    detail = FindingDetail(
        severity="INFO",
        category="STYLE",
        description="Missing docstring.",
        evidence_graph=[]
    )
    finding = FindingSchema(target, provenance, detail)
    
    # Save it twice to test cache hit
    storage.save_finding(finding)
    storage.save_finding(finding)
