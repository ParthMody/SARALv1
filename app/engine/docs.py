# app/engine/docs.py
from .scheme_config import get_scheme_config

def get_document_checklist(scheme_code: str, profile: dict) -> list[str]:
    """
    Generates documents dynamically from scheme_config.py
    """
    config = get_scheme_config(scheme_code)
    if not config:
        return ["Error: Scheme not found"]
    
    doc_rules = config.get("documents", {})
    
    # 1. Always add base documents
    final_list = list(doc_rules.get("base", []))
    
    # 2. Add Caste docs if user is marginalized AND scheme requires it
    if profile.get("caste_marginalized") == 1 and "caste_marginalized" in doc_rules:
        final_list.extend(doc_rules["caste_marginalized"])
        
    # 3. Add Rural docs if user is rural AND scheme requires it
    if profile.get("rural") == 1 and "rural" in doc_rules:
        final_list.extend(doc_rules["rural"])
        
    # 4. Add Scheme-specific special keys (like PMAY income/land proof)
    if "income_proof" in doc_rules and profile.get("income", 0) > 0:
        final_list.extend(doc_rules["income_proof"])
        
    if "land_proof" in doc_rules:
        final_list.extend(doc_rules["land_proof"])
        
    return final_list