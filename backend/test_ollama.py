import asyncio
from app.services.ollama_service import OllamaService
import traceback

def test():
    service = OllamaService()
    try:
        # Mock schema context
        schema = "Table: users\nColumns: id (int), name (varchar), age (int)"
        question = "How many users are there?"
        print("Sending prompt to Ollama...")
        res = service.generate_sql_and_dashboard(question, schema)
        print("Response:", res)
    except Exception as e:
        print("Error:", str(e))
        traceback.print_exc()

if __name__ == "__main__":
    test()
