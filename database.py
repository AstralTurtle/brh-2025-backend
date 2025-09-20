from pathlib import Path
from typing import Any, Dict, List, Optional

from tinydb import Query, TinyDB


class Database:
    def __init__(self, db_name: str):
        # Ensure the database directory exists
        Path(db_name).parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(db_name)

    def insert(self, model_class, obj):
        # Use the built-in to_json() method from ActivityPub models
        if hasattr(obj, "to_json"):
            data = obj.to_json()
        elif hasattr(obj, "model_dump"):
            data = obj.model_dump()
        else:
            data = obj

        # TinyDB automatically handles JSON serialization
        doc_id = self.db.insert(data)
        return doc_id

    def select(self, model_class, where: Optional[Dict[str, Any]] = None) -> List[Any]:
        if where:
            # Create TinyDB query
            query = Query()
            conditions = []
            for key, value in where.items():
                conditions.append(getattr(query, key) == value)

            # Combine conditions with AND
            final_query = conditions[0]
            for condition in conditions[1:]:
                final_query &= condition

            documents = self.db.search(final_query)
        else:
            documents = self.db.all()

        result = []
        for doc in documents:
            try:
                # Create model instance from the JSON data
                obj = model_class(**doc)
                result.append(obj)
            except Exception as e:
                print(f"Error creating {model_class.__name__} from document: {e}")
                continue

        return result

    def find_one(self, model_class, where: Dict[str, Any]):
        query = Query()
        conditions = []
        for key, value in where.items():
            conditions.append(getattr(query, key) == value)

        final_query = conditions[0]
        for condition in conditions[1:]:
            final_query &= condition

        doc = self.db.get(final_query)
        if doc:
            return model_class(**doc)
        return None

    def find_one_raw(self, where: Dict[str, Any]) -> Optional[Dict]:
        """Return raw document without model conversion"""
        query = Query()
        conditions = []
        for key, value in where.items():
            conditions.append(getattr(query, key) == value)

        final_query = conditions[0]
        for condition in conditions[1:]:
            final_query &= condition

        return self.db.get(final_query)

    def update(self, where: Dict[str, Any], update_data: Dict[str, Any]):
        query = Query()
        conditions = []
        for key, value in where.items():
            conditions.append(getattr(query, key) == value)

        final_query = conditions[0]
        for condition in conditions[1:]:
            final_query &= condition

        return self.db.update(update_data, final_query)

    def delete(self, where: Dict[str, Any]):
        query = Query()
        conditions = []
        for key, value in where.items():
            conditions.append(getattr(query, key) == value)

        final_query = conditions[0]
        for condition in conditions[1:]:
            final_query &= condition

        return self.db.remove(final_query)

    def insert_raw(self, data: Dict[str, Any]):
        """Insert raw dictionary data"""
        return self.db.insert(data)

    def all_raw(self) -> List[Dict]:
        """Get all documents as raw dictionaries"""
        return self.db.all()
