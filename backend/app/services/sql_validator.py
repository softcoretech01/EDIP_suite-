import re
from typing import Tuple

class SQLValidator:
    """
    Validates SQL queries to ensure they only contain safe operations.
    Allows: SELECT, GROUP BY, ORDER BY, JOIN, LIMIT
    Blocks: DELETE, UPDATE, DROP, ALTER, TRUNCATE, INSERT
    """
    
    BLOCKED_KEYWORDS = [
        "DELETE", "UPDATE", "DROP", "ALTER", "TRUNCATE", "INSERT",
        "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "EXEC", "EXECUTE",
        "MERGE", "CALL"
    ]

    @staticmethod
    def is_safe_query(query: str) -> Tuple[bool, str]:
        if not query or not query.strip():
            return False, "Query is empty"

        upper_query = query.upper()
        
        # Clean up markdown tags if LLM accidentally included them
        cleaned_query = re.sub(r'^```sql\s*', '', upper_query.strip(), flags=re.IGNORECASE)
        cleaned_query = re.sub(r'```\s*$', '', cleaned_query).strip()

        # Clean leading line comments
        while cleaned_query.startswith('--'):
            parts = cleaned_query.split('\n', 1)
            cleaned_query = parts[1].strip() if len(parts) > 1 else ""
            
        # Clean leading block comments
        while cleaned_query.startswith('/*'):
            end_idx = cleaned_query.find('*/')
            if end_idx != -1:
                cleaned_query = cleaned_query[end_idx+2:].strip()
            else:
                break

        if not cleaned_query.startswith("SELECT") and not cleaned_query.startswith("WITH"):
             return False, f"Query must be a SELECT statement. Received start: {cleaned_query[:20]}"

        # Check for blocked keywords using word boundaries to avoid matching inside table/column names
        for keyword in SQLValidator.BLOCKED_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, upper_query):
                return False, f"Blocked keyword found in query: {keyword}"
                
        # Basic check for multiple statements
        if ";" in cleaned_query:
            parts = [p for p in cleaned_query.split(";") if p.strip()]
            if len(parts) > 1:
                return False, "Multiple statements are not allowed."

        return True, "Query is safe"
