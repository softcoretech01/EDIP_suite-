import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

class GeminiService:
    def __init__(self):
        load_dotenv(override=True)
        # The user will need to provide their API key via env var
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("WARNING: GEMINI_API_KEY not set.")
        else:
            genai.configure(api_key=api_key)
        
        # Using the specified Gemini model or defaulting to gemini-2.5-pro
        model_name = os.getenv("GEMINI_MODEL", 'gemini-2.5-pro').strip().strip('"').strip("'")
        self.model = genai.GenerativeModel(model_name)

    def generate_sql_and_dashboard(self, question: str, schema_context: str) -> dict:
        """
        Uses Gemini to generate SQL based on the natural language question and retrieved schema context.
        Returns a JSON object matching the required format.
        """
        prompt = f"""
You are an expert SQL developer and Data Analyst.
Your task is to answer the user's question by generating a valid SQL query for the provided database schema.
You must also suggest a chart type for a dashboard and summarize the expected result.

Database Schema Context:
{schema_context}

User Question: {question}

You MUST return ONLY a valid JSON object with the following structure, with NO markdown formatting around it (no ```json):
{{
  "summary": "A brief 1-2 sentence explanation of what the query does",
  "sql": "The SQL query",
  "chart_type": "The best chart to visualize this data (e.g., 'BarChart', 'LineChart', 'PieChart', 'Table')",
  "data": [] 
}}
"""
        try:
            response = self.model.generate_content(prompt)
            # Clean up potential markdown blocks
            response_text = response.text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
                
            return json.loads(response_text.strip())
        except Exception as e:
            raise Exception(f"Failed to generate response from Gemini: {str(e)}")

    def synthesize_data(self, question: str, data: list) -> str:
        """
        Uses Gemini to generate a conversational summary of the raw database results.
        """
        # Truncate data if it's too large to prevent massive token usage
        if len(data) > 5:
            data = data[:5]
            truncated_note = " (Note: displaying first 5 rows of a larger dataset)"
        else:
            truncated_note = ""

        prompt = f"""
You are a helpful and professional Data Analyst assistant.
The user asked: "{question}"
We queried the database and got the following raw data{truncated_note}:
{json.dumps(data, indent=2, default=str)}

Please write a natural, conversational reply that answers the user's question directly using this data.
Do NOT just paste the raw JSON or a raw table. Summarize the key findings, totals, or list the relevant items in a human-friendly way.
Respond directly to the user.
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Data synthesis failed: {e}")
            return "I have fetched the data, but encountered an error while summarizing it."

