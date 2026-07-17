import subprocess
from pathlib import Path
from typing import List

class GitSync:
    """
    Handles synchronization of findings using git notes.
    """
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.notes_ref = "refs/notes/aegis"

    def _run_git(self, *args) -> str:
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "No note found" not in result.stderr:
            print(f"[Git Error] {' '.join(cmd)}: {result.stderr}")
        return result.stdout.strip()

    def attach_finding_to_commit(self, commit_sha: str, finding_hash: str):
        """
        Attaches a finding hash to a specific commit using git notes.
        """
        # Check if repo has any commits first
        check = subprocess.run(["git", "-C", str(self.repo_path), "rev-parse", "HEAD"], capture_output=True, text=True)
        if check.returncode != 0:
            print("[Sync] Repository has no commits. Delaying git-notes sync until first commit.")
            return

        if not commit_sha:
            commit_sha = check.stdout.strip()
            
        # Read existing notes if any
        existing_notes = self._run_git("notes", "--ref", self.notes_ref, "show", "--", commit_sha)
        
        findings = set()
        if existing_notes:
            for line in existing_notes.split('\n'):
                if line.startswith("findings:"):
                    # Parse "findings: hash1,hash2"
                    hashes = line.split(":", 1)[1].strip().split(",")
                    findings.update(h.strip() for h in hashes if h.strip())
                    
        findings.add(finding_hash)
        
        # Write back
        new_note = f"findings: {','.join(findings)}"
        self._run_git("notes", "--ref", self.notes_ref, "add", "-f", "-m", new_note, "--", commit_sha)
        print(f"[Sync] Attached finding {finding_hash} to commit {commit_sha}")

    def fetch_notes(self):
        """
        Fetches the engineer notes from origin.
        """
        print("[Sync] Fetching team analysis from origin...")
        self._run_git("fetch", "origin", f"{self.notes_ref}:{self.notes_ref}")

    def push_notes(self):
        """
        Pushes the engineer notes to origin.
        """
        print("[Sync] Pushing local analysis to origin...")
        self._run_git("push", "origin", self.notes_ref)
