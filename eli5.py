"""GreenLens — Plain English Summary"""

def generate_eli5(result: dict) -> str:
    name  = result.get("company_info", {}).get("name", result["company"])
    score = result["final_score"]
    flag  = result["flag"]
    best  = max(["e_score","s_score","g_score"], key=lambda k: result[k])
    worst = min(["e_score","s_score","g_score"], key=lambda k: result[k])
    label_map = {"e_score":"environmental","s_score":"social","g_score":"governance"}
    quality = "strong" if score >= 66 else "moderate" if score >= 41 else "concerning"
    return (
        f"{name} has an ESG score of {score}/100, reflecting {quality} sustainability practices. "
        f"It performs best on {label_map[best]} and has the most room to improve on {label_map[worst]}. "
        f"Overall risk is rated {flag} — {'suitable for ESG-conscious portfolios.' if flag=='LOW' else 'worth monitoring before allocation.' if flag=='MEDIUM' else 'due diligence recommended before investment.'}"
    )