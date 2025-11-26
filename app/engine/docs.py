# app/engine/docs.py

def get_document_checklist(scheme_code: str, profile: dict) -> list[str]:
    """
    Returns a deterministic list of documents required for the citizen.
    Logic is based on Scheme Rules + Citizen Profile.
    """
    docs = ["Aadhaar Card (Identity Proof)"] # Universal requirement
    
    # 1. PM UJJWALA YOJANA (Gas Connection)
    if scheme_code == "UJJ":
        docs.append("Bank Account Passbook (Front Page)")
        docs.append("Ration Card")
        docs.append("Passport Size Photo")
        
        # Conditional: Caste Certificate
        if profile.get("caste_marginalized") == 1:
            docs.append("Caste Certificate (SC/ST)")
            
        # Conditional: Address Proof (if Rural)
        if profile.get("rural") == 1:
            docs.append("Gram Panchayat Certificate")
            
    # 2. PM AWAS YOJANA (Housing)
    elif scheme_code == "PMAY":
        docs.append("Proof of Land Ownership (Patta/Registry)")
        docs.append("Bank Account Details")
        
        # Conditional: Income Proof
        if profile.get("income", 0) < 300000:
            docs.append("Income Certificate (EWS/LIG)")
        else:
            docs.append("Income Tax Return (ITR)")
            
    return docs