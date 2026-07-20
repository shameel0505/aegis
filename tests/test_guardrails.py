import ast
from aegis.guardrails import filter_findings, analyze_safe_regions
from aegis.schema import FindingDetail

def test_ast_guardrails_filters_safe_fastapi_injection():
    """
    Proves that Aegis does not hallucinate warnings on standard
    FastAPI Dependency Injection (e.g. Depends()).
    """
    source_code = """
from fastapi import Depends

def get_db():
    pass

def read_items(db = Depends(get_db)):
    return []
"""
    
    # Simulate a raw finding from the LLM complaining about 'Depends' returning None
    raw_findings = [
        FindingDetail(
            severity="CRITICAL",
            category="ARCHITECTURE",
            description="The function read_items relies on Depends which might return None.",
            faulty_snippet="db = Depends(get_db)",
            evidence_graph=[{"type": "CALLER", "to": "test"}]
        )
    ]
    
    safe_regions = analyze_safe_regions("test.py", source_code, "fastapi")
    filtered = filter_findings(raw_findings, source_code, safe_regions)
    # The guardrails should deterministically filter out this hallucination
    assert len(filtered) == 0

def test_ast_guardrails_filters_kwonlyargs_fastapi_injection():
    """
    Proves that Aegis correctly identifies kwonlyargs in modern FastAPI endpoints.
    """
    source_code = """
from fastapi import Depends

def get_db():
    pass

def read_items(*, db = Depends(get_db)):
    return []
"""
    
    raw_findings = [
        FindingDetail(
            severity="CRITICAL",
            category="ARCHITECTURE",
            description="The function read_items relies on Depends which might return None.",
            faulty_snippet="db = Depends(get_db)",
            evidence_graph=[{"type": "CALLER", "to": "test"}]
        )
    ]
    
    safe_regions = analyze_safe_regions("test.py", source_code, "fastapi")
    filtered = filter_findings(raw_findings, source_code, safe_regions)
    assert len(filtered) == 0

def test_ast_guardrails_allows_genuine_sql_injection():
    """
    Proves that Aegis allows genuine security vulnerabilities
    to pass through the guardrails.
    """
    source_code = """
import sqlite3

def get_user(username: str):
    conn = sqlite3.connect('test.db')
    cursor = conn.cursor()
    # SQL INJECTION!
    cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
"""
    
    raw_findings = [
        FindingDetail(
            severity="CRITICAL",
            category="SECURITY",
            description="Raw f-string used in SQL execution.",
            faulty_snippet="cursor.execute(f\"SELECT * FROM users WHERE username = '{username}'\")",
            evidence_graph=[{"type": "CALLER", "to": "test"}]
        )
    ]
    
    safe_regions = analyze_safe_regions("test.py", source_code, "generic")
    filtered = filter_findings(raw_findings, source_code, safe_regions)
    # The guardrails should NOT filter this, as it is a genuine bug
    assert len(filtered) == 1
    assert filtered[0].category == "SECURITY"
