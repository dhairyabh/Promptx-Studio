from database import get_db

db = get_db()
if db is not None:
    print("MongoDB Connection Successful!")
else:
    print("MongoDB Connection Failed.")
