import json
from typing import List, Dict, Any

def refine_strategic_questions(context: str, llm_client, system_prompt: str, count: int = 3) -> List[str]:
    """
    Uses the Thrawn persona to analyze repo context and identify high-impact unknowns.
    """
    prompt = f"""
    Analyze the current repository context. Identify strategic flaws, architectural oversights, 
    or missing 'Intent' details required for a Senior Product Manager to succeed.
    
    Context:
    {context}
    
    Formulate exactly {count} surgical, high-impact clarifying questions. 
    Focus on:
    1. Primary Objective (if missing or vague)
    2. Target Audience/Users
    3. Technical Stack Constraints
    4. Key Success Metrics
    
    Return the questions as a JSON list of strings: ["Question 1", "Question 2"]
    """
    try:
        # Request JSON from the LLM client
        response = llm_client.generate(prompt, system_instruction=system_prompt, json_format=True)
        questions = llm_client.parse_json_response(response)
        
        if isinstance(questions, list):
            return [str(q) for q in questions]
        return []
    except Exception as e:
        print(f"[clarification_engine] Refinement Error: {e}")
        return []

def analyze_answer_for_roadmap_impact(question: str, answer: str, current_roadmap: str, llm_client, system_prompt: str) -> List[Dict[str, Any]]:
    """
    Analyzes a user's answer to determine if the Roadmap needs to be refactored.
    """
    prompt = f"""
    A strategic question has been answered. Determine the impact on the Roadmap.
    Question: {question}
    Answer: {answer}
    
    Current Roadmap:
    {current_roadmap}
    
    Return a list of roadmap actions in JSON format:
    [
        {{"action": "redact", "pattern": "item to remove"}},
        {{"action": "add", "section": "Phase 1", "item": "new task based on answer"}}
    ]
    """
    try:
        response = llm_client.generate(prompt, system_instruction=system_prompt, json_format=True)
        result = llm_client.parse_json_response(response)
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        print(f"[clarification_engine] Impact Analysis Error: {e}")
        return []

def get_onboarding_sequence() -> List[str]:
    """
    Returns the baseline 'Must-Ask' questions for a brand new repository.
    This ensures consistency during the first run of Thrawn.
    """
    return [
        "What is the Primary Objective of this repository? (Elevator pitch)",
        "Who is the target user for this project?",
        "Are there any hard technical constraints (e.g., must use Python, must run on-prem)?",
        "How will we measure success for this project?"
    ]
