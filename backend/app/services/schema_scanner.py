from sqlalchemy import create_engine, inspect
from typing import List, Dict, Any

class SchemaScanner:
    def __init__(self, connection_url: str):
        self.engine = create_engine(connection_url)
        self.inspector = inspect(self.engine)

    def scan_schema(self) -> List[Dict[str, Any]]:
        """
        Scans the database and returns a list of tables and their columns.
        """
        schema_data = []
        table_names = self.inspector.get_table_names()

        for table_name in table_names:
            columns = self.inspector.get_columns(table_name)
            pk_constraint = self.inspector.get_pk_constraint(table_name)
            fk_constraints = self.inspector.get_foreign_keys(table_name)

            pk_columns = pk_constraint.get('constrained_columns', [])
            fk_columns = [fk['constrained_columns'][0] for fk in fk_constraints if fk['constrained_columns']]

            table_info = {
                "table_name": table_name,
                "description": f"Extracted from database schema.",
                "columns": []
            }

            for col in columns:
                col_info = {
                    "column_name": col['name'],
                    "data_type": str(col['type']),
                    "is_primary_key": col['name'] in pk_columns,
                    "is_foreign_key": col['name'] in fk_columns,
                    "description": col.get('comment', '') or ''
                }
                table_info["columns"].append(col_info)

            schema_data.append(table_info)

        return schema_data
