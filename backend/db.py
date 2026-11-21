from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")

db = client["medichain"]

users_collection = db["users"]

doctor_profiles_collection = db["doctor_profiles"]

hospitals_collection = db["hospitals"]

records_collection = db["records"]

summary_collection = db["summary"]

visits_collection = db["visits"]

notifications_collection = db["notifications"]

audit_collection = db["audit_logs"]

access_collection = db["access_control"]

sessions_collection = db["sessions"]

diseases_collection = db["diseases"]