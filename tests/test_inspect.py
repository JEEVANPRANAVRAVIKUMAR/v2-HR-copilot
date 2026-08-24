import json
from config import get_settings
from groq import Groq

def test_list_groq_models():
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)
    
    models = client.models.list()
    model_ids = [m.id for m in models.data]
    
    with open("groq_models.json", "w") as f:
        json.dump(model_ids, f, indent=2)
    
    assert len(model_ids) > 0
