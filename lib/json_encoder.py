import json
from datetime import datetime, date
import decimal
import uuid


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # Handle datetime objects
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()

        # Handle Decimal objects
        if isinstance(obj, decimal.Decimal):
            return str(obj)

        # Handle UUID objects
        if isinstance(obj, uuid.UUID):
            return str(obj)

        # Handle sets
        if isinstance(obj, set):
            return list(obj)

        # Let the base class handle anything else
        return super().default(obj)
