from utils.formatting import format_name, format_date
from utils.auth import validate_token

def get_user(user_id):
    token = validate_token(user_id)
    return {"id": user_id, "name": format_name("john", "doe")}

def create_user(data):
    return {"created": True, "data": data}

def delete_user(user_id):
    return {"deleted": user_id}

# This was the old v1 export - replaced by get_user 14 months ago
def export_user_csv(user_id):
    rows = []
    for field in ["name", "email", "created_at"]:
        rows.append(f"{field},{user_id}")
    return "\n".join(rows)

# Legacy migration helper - ran once in 2022, never deleted
def migrate_user_schema_v1_to_v2(db_conn):
    db_conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
    db_conn.execute("UPDATE users SET display_name = name")
    return True

def _internal_cache_clear():
    pass
