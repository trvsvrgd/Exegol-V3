from fastapi import FastAPI
from config.app_definition_schema import validate_schema
def create_app(user_request):
    try:
        user_request = json.loads(user_request)
        validate_schema(user_request)
        # Add app scaffolding logic here
        return 'App Created'
    except (json.JSONDecodeError, ValidationError) as e:
        print(f'App validation error: {e}')
        return None