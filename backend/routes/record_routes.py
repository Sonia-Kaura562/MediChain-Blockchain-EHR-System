from middleware.auth_middleware import jwt_required
from middleware.role_middleware import role_required
from flask import (

    Blueprint,

    request,

    jsonify,

    Response
)
from datetime import datetime

import uuid

from db import (
    summary_collection,
    records_collection,
    users_collection,
    access_collection,
    visits_collection,
    notifications_collection,
    diseases_collection
)

from services.ipfs_service import PinataService

from middleware.access_middleware import access_required

record_bp = Blueprint('record', __name__)

ipfs = PinataService()

# =========================================
# UPDATE CURRENT DISEASE SUMMARY
# =========================================
def update_summary(
    patient_id,
    disease,
    status,
    doctor_id,
    hospital_id
):

    summary = summary_collection.find_one({
        "patientId": patient_id
    })

    # First entry
    if not summary:

        summary_collection.insert_one({

            "patientId": patient_id,

            "currentDiseases": [

                {
                    "disease": disease,
                    "status": status,
                    "doctorId": doctor_id,
                    "hospitalId": hospital_id,
                    "startedAt": datetime.utcnow()
                }
            ],

            "lastUpdated": datetime.utcnow()
        })

        return

    diseases = summary["currentDiseases"]

    disease_exists = False

    for d in diseases:

        if d["disease"] == disease:

            disease_exists = True

            d["status"] = status

            d["doctorId"] = doctor_id

            d["hospitalId"] = hospital_id

            if status.lower() == "cured":

                d["curedAt"] = datetime.utcnow()

    # New disease
    if not disease_exists:

        diseases.append({

            "disease": disease,

            "status": status,

            "doctorId": doctor_id,

            "hospitalId": hospital_id,

            "startedAt": datetime.utcnow()
        })

    summary_collection.update_one(

        {
            "patientId": patient_id
        },

        {
            "$set": {

                "currentDiseases": diseases,

                "lastUpdated": datetime.utcnow()
            }
        }
    )

# =========================================
# CREATE VISIT
# =========================================
@record_bp.route(
    '/create-visit',
    methods=['POST']
)
@jwt_required
@access_required("update")
def create_visit():

    try:

        if request.user["role"] != "doctor":

            return jsonify({
                "error": "Only doctors can create visits"
            }), 403

        data = request.json

        patient_id = data.get(
            "patientId"
        )

        if not patient_id:

            return jsonify({
                "error": "patientId required"
            }), 400
        
        patient = users_collection.find_one({

            "userId": patient_id,

            "role": "patient"
        })
        
        if not patient:

            return jsonify({

                "error":
                "Patient not found"

            }), 404
        hospital_id = data.get(
            "hospitalId"
        )

        primary_disease = data.get(
            "primaryDisease"
        )

        medicines = data.get(
            "medicines",
            []
        )

        patient_visit_number = (

            visits_collection.count_documents({

                "patientId": patient_id

            }) + 1
        )

        doctor_visit_number = (

            visits_collection.count_documents({

                "patientId": patient_id,

                "doctorId": request.user["userId"]

            }) + 1
        )
        visit_id = (

            "VIS-"

            + uuid.uuid4()

            .hex[:8]

            .upper()
        )

        visit = {

            "visitId":
            visit_id,

           "visitNumber":
            patient_visit_number,

            "doctorVisitNumber":
            doctor_visit_number,

            "patientId":
            patient_id,

            "doctorId":
            request.user["userId"],

            "hospitalId":
            hospital_id,

            "primaryDisease":
            primary_disease,

            "medicines":
            medicines,

            "recordIds":
            [],

            "numberOfRecords":
            0,

            "visitStatus":
            "active",

            "createdAt":
            datetime.utcnow()
        }

        visits_collection.insert_one(
            visit
        )

        existing_disease = diseases_collection.find_one({

            "patientId": patient_id,

            "diseaseName": primary_disease,

            "status": {
                "$ne": "cured"
            }
        })

        if not existing_disease:

            disease_id = (

                "DIS-"

                + uuid.uuid4()

                .hex[:8]

                .upper()
            )

            diseases_collection.insert_one({

                "diseaseId": disease_id,

                "patientId": patient_id,

                "diseaseName": primary_disease,

                "status": "active",

                "statusLabel": "Under Treatment",

                "primaryDoctorId": request.user["userId"],

                "doctorIds": [
                    request.user["userId"]
                ],

                "diagnosedAt": datetime.utcnow(),

                "curedAt": None,

                "createdAt": datetime.utcnow()
            })

        else:

            diseases_collection.update_one(

                {
                    "_id": existing_disease["_id"]
                },

                {
                    "$addToSet": {

                        "doctorIds":
                        request.user["userId"]
                    }
                }
            )

        return jsonify({

            "message":
            "Visit created",

            "visitId":
            visit_id
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500
    
# =========================================
# GET LATEST VISIT
# =========================================
@record_bp.route(
    '/latest-visit',
    methods=['GET']
)
@jwt_required
def latest_visit():

    try:

        user_id = request.user["userId"]

        role = request.user["role"]

        if role != "patient":

            return jsonify({
                "error":
                "Only patients can access latest visit"
            }), 403

        visit = visits_collection.find_one(

            {
                "patientId":
                user_id
            },

            sort=[
                (
                    "createdAt",
                    -1
                )
            ]
        )

        if not visit:

            return jsonify({
                "message":
                "No visits found"
            }), 404

        visit["_id"] = str(
            visit["_id"]
        )

        doctor = None

        if visit.get("doctorId"):

            doctor = users_collection.find_one(

            {
                "userId":
                visit["doctorId"],

                "role":
                "doctor"
            },

            {
                "_id": 0,
                "password": 0
            }
        )

        records = list(

            records_collection.find(

                {
                    "recordId": {
                        "$in": visit.get(
                            "recordIds",
                            []
                        )
                    }
                },

                {
                    "_id": 0,
                    "ipfsHash": 0
                }
            ).sort(
                "uploadedAt",
                -1
            )
        )
        return jsonify({

        "visit": visit,

        "doctor": doctor,

        "records": records
    })

    except Exception as e:

        return jsonify({
            "error":
            str(e)
        }), 500
# =========================================
# BASIC IPFS UPLOAD
# =========================================
@record_bp.route('/upload', methods=['POST'])
@jwt_required
def upload():

    try:

        # =====================================
        # FILE CHECK
        # =====================================
        if 'file' not in request.files:

            return jsonify({
                "error": "No file provided"
            }), 400

        file = request.files[

            'file'
        ]

        if not file.filename:

            return jsonify({
                "error": "No file selected"
            }), 400

        # =====================================
        # USER INFO
        # =====================================
        user_id = request.user[

            "userId"
        ]

        role = request.user[

            "role"
        ]

        # =====================================
        # FORM DATA
        # =====================================
        patient_id = request.form.get(

            "patientId"
        )

        record_type = request.form.get(

            "recordType"
        )

        title = request.form.get(

            "title"
        )

        description = request.form.get(

            "description"
        )

        visit_id = request.form.get(
            "visitId"
        )
        # =====================================
        # VALID RECORD TYPES
        # =====================================
        allowed_record_types = [

            "prescription",

            "xray",

            "mri",

            "ct_scan",

            "blood_test",

            "lab_report",

            "diagnosis",

            "vaccination",

            "discharge_summary",

            "insurance",

            "other"
        ]

        if (

            not record_type

            or

            record_type

            not in allowed_record_types
        ):

            return jsonify({

                "error":

                "Invalid record type"
            }), 400

        # =====================================
        # REQUIRED FIELDS
        # =====================================
        if (

            not title

            or

            not title.strip()
        ):

            return jsonify({

                "error":

                "Title required"
            }), 400

        # =====================================
        # FILE TYPE VALIDATION
        # =====================================
        allowed_types = [

            "application/pdf",

            "image/jpeg",

            "image/png",

            "image/jpg"
        ]

        if (

            file.content_type

            not in allowed_types
        ):

            return jsonify({

                "error":

                "Only PDF, JPG, JPEG and PNG files allowed"

            }), 400

        # =====================================
        # FILE SIZE LIMIT
        # 10 MB
        # =====================================
        file.seek(

            0,

            2
        )

        size = file.tell()

        file.seek(0)

        if size > 10 * 1024 * 1024:

            return jsonify({

                "error":

                "File size exceeds 10MB"

            }), 400

        # =====================================
        # PATIENT UPLOAD
        # =====================================
        if role == "patient":

            if patient_id:

                return jsonify({

                    "error":

                    "Patients cannot provide patientId"

                }), 403

            patient_id = user_id

        # =====================================
        # DOCTOR UPLOAD
        # =====================================
        elif role == "doctor":

            if not patient_id:

                return jsonify({
                    "error": "patientId required"
                }), 400

            if not visit_id:

                return jsonify({
                    "error": "visitId required"
                }), 400

            visit = visits_collection.find_one({

                "visitId":
                visit_id,

                "patientId":
                patient_id
            })

            if not visit:

                return jsonify({
                    "error":
                    "Visit not found"
                }), 404

        else:

            return jsonify({

                "error":

                "Only patient or doctor can upload"

            }), 403

        # =====================================
        # FIND LATEST ACTIVE RECORD
        # =====================================
        old_replaceable_record = None

        if role == "patient":

            latest_active_record = (

                records_collection.find_one({

                    "patientId":

                    patient_id,

                    "recordType":

                    record_type,

                    "isArchived":

                    False

                },

                sort=[(

                    "uploadedAt",

                    -1
                )])
            )

            # =================================
            # VERIFIED RECORD CANNOT REPLACE
            # =================================
            if latest_active_record:

                if (

                    latest_active_record[

                        "status"
                    ]

                    == "verified"
                ):

                    return jsonify({

                        "error":

                        "Verified records cannot be replaced"

                    }), 403

                # =============================
                # ONLY REPLACE
                # pending_verification
                # or flagged
                # =============================
                if (

                    latest_active_record[

                        "status"
                    ]

                    in [

                        "pending_verification",

                        "flagged"
                    ]
                ):

                    old_replaceable_record = (

                        latest_active_record
                    )

        # =====================================
        # CHECK PATIENT EXISTS
        # =====================================
        patient = users_collection.find_one({

            "userId":

            patient_id,

            "role":

            "patient"
        })

        if not patient:

            return jsonify({

                "error":

                "Patient not found"

            }), 404

        # =====================================
        # UPLOAD TO IPFS
        # =====================================
        try:

            ipfs_hash = ipfs.upload(

                file
            )

        except Exception as e:

            return jsonify({

                "error":

                f"IPFS upload failed: {str(e)}"

            }), 500

        # =====================================
        # RECORD STATUS
        # =====================================
        status = (

            "verified"

            if role == "doctor"

            else "pending_verification"
        )

        # =====================================
        # GENERATE RECORD ID
        # =====================================
        record_id = (

            "REC-"

            + uuid.uuid4()

            .hex[:8]

            .upper()
        )

        # =====================================
        # SAVE RECORD
        # =====================================
        record = {

            "recordId":

            record_id,

            "patientId":

            patient_id,

            "doctorId":

            user_id,
            
            "visitId":

            visit_id
            if role == "doctor"

            else None,

            "recordVersion":

            1,

            "uploadedBy":

            user_id,

            "uploadedByRole":

            role,

            "recordType":

            record_type,

            "title":

            title.strip(),

            "description":

            description.strip()

            if description

            else "",

            "fileName":

            file.filename,

            "fileType":

            file.content_type,

            "ipfsHash":

            ipfs_hash,

            "blockchainTxHash":

            None,

            "status":

            status,

            "flagReason":

            None,

            "verifiedBy":

            user_id

            if role == "doctor"

            else None,

            "verifiedAt":

            datetime.utcnow()

            if role == "doctor"

            else None,

            "isArchived":

            False,

            "archivedAt":

            None,

            "archiveReason":

            None,

            "uploadedAt":

            datetime.utcnow()
        }

        result = records_collection.insert_one(

            record
        )

        if role == "doctor":

            update_data = {

                "$push": {
                    "recordIds": record_id
                },

                "$inc": {
                    "numberOfRecords": 1
                }
            }

            visits_collection.update_one(

                {
                    "visitId": visit_id
                },

                update_data
            )

        # =====================================
        # ARCHIVE OLD RECORD
        # =====================================
        if old_replaceable_record:

            records_collection.update_one(

                {
                    "_id":

                    old_replaceable_record[

                        "_id"
                    ]
                },

                {
                    "$set": {

                        "isArchived":

                        True,

                        "archivedAt":

                        datetime.utcnow(),

                        "archiveReason":

                        "Patient replaced uploaded record",

                        "replacedBy":

                        record_id
                    }
                }
            )

            records_collection.update_one(

                {
                    "_id":

                    result.inserted_id
                },

                {
                    "$set": {

                        "replacesRecord":

                        old_replaceable_record[

                            "recordId"
                        ]
                    }
                }
            )
        return jsonify({

        "message":

        "Record uploaded successfully",

        "recordId":

        record_id,

        "ipfsHash":

        ipfs_hash
    })

    except Exception as e:

        return jsonify({

            "error":

            str(e)
        }), 500
    
# =========================================
# VIEW / DOWNLOAD RECORD
# =========================================
@record_bp.route(

    '/view-record/<record_id>',

    methods=['GET']
)
@jwt_required
@access_required("read")
def view_record(record_id):

    try:

        record = records_collection.find_one({

            "recordId":

            record_id
        })

        if not record:

            return jsonify({

                "error":

                "Record not found"

            }), 404

        user = request.user

        role = user[

            "role"
        ]

        user_id = user[

            "userId"
        ]

        # =====================================
        # PATIENT CAN VIEW OWN RECORD
        # =====================================
        if role == "patient":

            if record["patientId"] != user_id:

                return jsonify({

                    "error":

                    "Unauthorized access"

                }), 403

        # =====================================
        # FETCH FROM IPFS
        # =====================================
        file_content = ipfs.fetch(

            record["ipfsHash"]
        )

        print("========== IPFS DEBUG ==========")
        print("HASH:", record["ipfsHash"])
        print("TYPE:", type(file_content))

        if file_content:
            print("SIZE:", len(file_content))
        else:
            print("EMPTY CONTENT")

        return Response(

            file_content,

            mimetype=record[

                "fileType"
            ],

            headers={

                "Content-Disposition":

                f'inline; filename={record["fileName"]}'
            }
        )

    except Exception as e:

        return jsonify({

            "error":

            str(e)
        }), 500
    
# =========================================
# DOWNLOAD RECORD
# =========================================
@record_bp.route(

    '/download-record/<record_id>',

    methods=['GET']
)
@jwt_required
@access_required("read")
def download_record(record_id):

    try:

        record = records_collection.find_one({

            "recordId":

            record_id
        })

        if not record:

            return jsonify({

                "error":

                "Record not found"

            }), 404

        user = request.user

        role = user[

            "role"
        ]

        user_id = user[

            "userId"
        ]

        # =====================================
        # PATIENT CAN DOWNLOAD OWN RECORD
        # =====================================
        if role == "patient":

            if record["patientId"] != user_id:

                return jsonify({

                    "error":

                    "Unauthorized access"

                }), 403

        # =====================================
        # FETCH FROM IPFS
        # =====================================
        file_content = ipfs.fetch(

            record["ipfsHash"]
        )

        print("========== IPFS DEBUG ==========")
        print("HASH:", record["ipfsHash"])
        print("TYPE:", type(file_content))

        if file_content:
            print("SIZE:", len(file_content))
        else:
            print("EMPTY CONTENT")
        return Response(

            file_content,

            mimetype=record[

                "fileType"
            ],

            headers={

                "Content-Disposition":

                f'attachment; filename={record["fileName"]}'
            }
        )

    except Exception as e:

        return jsonify({

            "error":

            str(e)
        }), 500
    
@record_bp.route(
    '/my-records',
    methods=['GET']
)
@jwt_required
def my_records():

    try:

        user_id = request.user["userId"]
        role = request.user["role"]

        if role != "patient":

            return jsonify({
                "error": "Only patients can access this endpoint"
            }), 403

        records = list(
            records_collection.find(
                {
                    "patientId": user_id,
                    "isArchived": False
                },
                {
                    "_id": 0,
                    "ipfsHash": 0
                }
            ).sort(
                "uploadedAt",
                -1
            )
        )

        return jsonify(records)

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500