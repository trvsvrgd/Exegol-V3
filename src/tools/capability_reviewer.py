import json
from typing import List, Dict, Any, Optional

def map_requirement_to_capability(requirement: Dict[str, Any], capabilities: List[Dict[str, Any]], llm_client: Any = None) -> Dict[str, Any]:
    """Maps a regulatory requirement to the most relevant system capability.
    
    If llm_client is provided, uses semantic analysis to find matches beyond simple ID equality.
    """
    req_desc = requirement.get("description", "")
    req_summary = requirement.get("summary", "")
    target_id = requirement.get("required_capability_id")
    
    # 1. Simple ID Match
    for cap in capabilities:
        if cap.get("id") == target_id:
            return {
                "matched": True,
                "capability": cap,
                "match_type": "exact_id",
                "confidence": 1.0
            }
            
    # 2. Semantic Match (Optional LLM path)
    if llm_client:
        prompt = f"""
        Regulatory Requirement: {req_summary} - {req_desc}
        System Capabilities: {json.dumps(capabilities, indent=2)}
        
        Identify which system capability (if any) most closely addresses this requirement.
        Return a JSON object with:
        - 'matched': boolean
        - 'capability_id': string id or null
        - 'reasoning': string explaining the match or lack thereof
        - 'confidence': float 0.0-1.0
        """
        try:
            response = llm_client.generate(prompt, json_format=True)
            result = llm_client.parse_json_response(response)
            if result.get("matched") and result.get("capability_id"):
                for cap in capabilities:
                    if cap.get("id") == result["capability_id"]:
                        return {
                            "matched": True,
                            "capability": cap,
                            "match_type": "semantic",
                            "confidence": result.get("confidence", 0.5),
                            "reasoning": result.get("reasoning")
                        }
        except Exception as e:
            print(f"[capability_reviewer] LLM matching failed: {e}")

    return {
        "matched": False,
        "capability": None,
        "match_type": "none",
        "confidence": 0.0
    }

def get_implemented_capabilities(capabilities: List[Dict[str, Any]]) -> List[str]:
    """Returns list of IDs for capabilities marked as implemented."""
    return [c["id"] for c in capabilities if c.get("implemented")]
