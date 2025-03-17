import json
import re
from typing import Any, Dict, List, Tuple

class BaseModel:
    table_name: str = ""
    fields: Dict[str, str] = {}

    @classmethod
    def _validate_fields(cls, fields: List[str]) -> None:
        for field in fields:
            if field not in cls.fields:
                raise ValueError(f"Invalid field: {field}")

    @classmethod
    def _validate_conditions(cls, conditions: List[Tuple[str, str, Any]]) -> None:
        for condition in conditions:
            if len(condition) != 3:
                raise ValueError(f"Invalid condition: {condition}")
            if condition[0] not in cls.fields:
                raise ValueError(f"Invalid condition field: {condition[0]}")

    @classmethod
    def _convert(cls, value: Any) -> str:
        if isinstance(value, str):
            # Check SQL statement
            sql_stat = re.match(r"select|insert|update|delete", str(value))
            if sql_stat:
                return value
            # Escape string with single quotes
            return f"'{value}'"
        
        # Convert dict to JSON string
        if isinstance(value, dict):
            return f"'{json.dumps(value)}'"
        
        # Convert other types to string
        return str(value)
    
    @classmethod
    def insert(cls, **kwargs: Any) -> str:
        cls._validate_fields(kwargs.keys())

        keys = ", ".join(kwargs.keys())
        values = ", ".join(cls._convert(val) for val in kwargs.values())
        sql = f"""
        INSERT INTO {cls.table_name} 
        ({keys})
        VALUES 
        ({values})
        """
        return sql

    @classmethod
    def update(cls, conditions: List[Tuple[str, str, Any]], **kwargs: Any) -> str:
        cls._validate_fields(list(kwargs.keys()))
        cls._validate_conditions(conditions)
    
        set_clause = ', '.join(f"{col} = {cls._convert(val)}" for col, val in kwargs.items())
        conditions_clause = ' AND '.join(f"{col} {op} {cls._convert(val)}" for col, op, val in conditions)
        sql = f"""
        UPDATE {cls.table_name} 
        SET {set_clause} 
        WHERE {conditions_clause}
        """
        return sql

class User(BaseModel):
    table_name = "users"
    fields = {
        "name": "TEXT",
        "email": "TEXT",
        "age": "INTEGER",
        "info": "JSON",
        "sn": "TEXT",
    }

if __name__ == "__main__":
    info = {
        "address": "123 Main St",
        "city": "Springfield",
        "state": "IL",
    }
    sql = User.insert(name="Alice", email="alice@example.com", age=30, info=info,
                sn="select x.sn from TABLE x where x.id = '123'")
    print(sql)

    conditions = [
        ("name", "=", "Alice"),
        ("age", "<", 10),
    ]
    sql = User.update(conditions, name="Alice Johnson", email="alice@example.com", age=30)
    print(sql)
