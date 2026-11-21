from db import (
    users_collection,
    doctor_profiles_collection
)

from datetime import datetime

doctors = users_collection.find({
    "role": "doctor"
})

for doctor in doctors:

    existing = doctor_profiles_collection.find_one({

        "doctorId":
        doctor["userId"]
    })

    if existing:
        continue

    doctor_profiles_collection.insert_one({

        "doctorId":
        doctor["userId"],

        "fullName":
        doctor.get(
            "fullName",
            ""
        ),

        "email":
        doctor.get(
            "email",
            ""
        ),

        "specialization": "",

        "qualification": "",

        "experienceYears": 0,

        "hospitalName": "",

        "department": "",

        "profileImage": "",

        "about": "",

        "availability": [],

        "createdAt":
        datetime.utcnow()
    })

print(
    "Doctor profiles migration completed"
)