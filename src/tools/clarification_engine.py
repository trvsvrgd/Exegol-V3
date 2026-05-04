import json
from typing import List, Dict, Any

def refine_strategic_questions(context: str, llm_client, system_prompt: str, count: int = 3) -> List[str]:
    """
    Uses an LLM to analyze the repository context and formulate precise, strategic clarifying questions.
    """
    prompt = f"""
    Analyze the following repository context and identify strategic flaws, architectural oversights, or missing intent details.
    Formulate exactly {count} surgical, high-impact clarifying questions for the user to drive the next evolution of the application.
    
    Context:
    {context}
    
    Return the questions as a JSON list of strings.
    """
    try:
        response = llm_client.generate(prompt, system_instruction=system_prompt)
        questions = llm_client.parse_json_response(response)
        if isinstance(questions, list):
            return [str(q) for q in questions]
        return []
    except Exception as e:
        print(f"[clarification_engine] Error: {e}")
        return []

def analyze_answer_for_roadmap_impact(question: str, answer: str, current_roadmap: str, llm_client, system_prompt: str) -> List[Dict[str, Any]]:
    """
    Analyzes a user's answer and determines its impact on the project roadmap.
    """
    prompt = f"""
    The user has provided an answer to a strategic question.
    Question: {question}
    Answer: {answer}
    
    Current Roadmap:
    {current_roadmap}
    
    Determine if this answer requires changes to the roadmap (adding, redacting, or updating items).
    Return a list of actions in JSON format:
    [
        {{"action": "redact", "pattern": "string to match"}},
        {{"action": "add", "section": "Phase X", "item": "new item"}}
    ]
    If no changes are needed, return [].
    """
    try:
        response = llm_client.generate(prompt, system_instruction=system_prompt)
        actions = llm_client.parse_json_response(response)
        if isinstance(actions, list):
            return actions
        return []
    except Exception as e:
        print(f"[clarification_engine] Error analyzing answer: {e}")
        return []
