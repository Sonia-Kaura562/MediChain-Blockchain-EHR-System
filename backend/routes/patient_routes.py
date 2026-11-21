from flask import Blueprint, request, jsonify

from middleware.auth_middleware import jwt_required

from middleware.role_middleware import role_required

from middleware.access_middleware import access_required

from services.audit_service import log_action

from services.blockchain_service import (

    grant_access,

    revoke_access
)

from db import (
    records_collection,
    summary_collection,
    access_collection,
    visits_collection,
    diseases_collection,
    users_collection
)
from datetime import datetime
patient_bp = Blueprint('patient', __name__)
# =========================================
# GRANT ACCESS
# =========================================
@patient_bp.route('/grant-access', methods=['POST'])
@jwt_required
@role_required(["patient"])
def grant():

    try:

        data = request.json

        logged_in_patient = request.user["userId"]

        if data["patientId"] != logged_in_patient:

            return jsonify({
                "error": "Unauthorized patient access"
            }), 403

        required_fields = [

            "patientId",

            "doctorWallet",

            "canRead",

            "canUpdate",

            "duration"
        ]

        for field in required_fields:

            if field not in data:

                return jsonify({
                    "error": f"{field} required"
                }), 400

        tx = grant_access(data)
        expiry_time = datetime.utcnow().timestamp() + data["duration"]

        access_collection.update_one(

            {
                "patientId": data["patientId"],
                "doctorWallet": data["doctorWallet"]
            },

            {
                "$set": {

                    "patientId": data["patientId"],

                    "doctorWallet": data["doctorWallet"],

                    "canRead": data["canRead"],

                    "canUpdate": data["canUpdate"],

                    "expiryTime": expiry_time
                }
            },

            upsert=True
        )
        # =====================================
        # AUDIT LOG
        # =====================================
        log_action(

            request.user["userId"],

            request.user["role"],

            "GRANT_ACCESS",

            data["patientId"]
        )

        return jsonify({

            "message": "Access granted",

            "txHash": tx
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# REVOKE ACCESS
# =========================================
@patient_bp.route('/revoke-access', methods=['POST'])
@jwt_required
@role_required(["patient"])
def revoke():

    try:

        data = request.json

        logged_in_patient = request.user["userId"]

        if data["patientId"] != logged_in_patient:

            return jsonify({
                "error": "Unauthorized patient access"
            }), 403

        required_fields = [

            "patientId",

            "doctorWallet",

            "revokeRead",

            "revokeUpdate"
        ]

        for field in required_fields:

            if field not in data:

                return jsonify({
                    "error": f"{field} required"
                }), 400

        tx = revoke_access(data)

        update_fields = {}

        if data["revokeRead"]:

            update_fields["canRead"] = False

        if data["revokeUpdate"]:

            update_fields["canUpdate"] = False

        access_collection.update_one(

            {
                "patientId": data["patientId"],
                "doctorWallet": data["doctorWallet"]
            },

            {
                "$set": update_fields
            }
        )

        # =====================================
        # AUDIT LOG
        # =====================================
        log_action(

            request.user["userId"],

            request.user["role"],

            "REVOKE_ACCESS",

            data["patientId"]
        )

        return jsonify({

            "message": "Access revoked",

            "txHash": tx
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500

# =========================================
# HISTORY API
# =========================================
@patient_bp.route('/history/<patient_id>', methods=['GET'])
@jwt_required
@access_required("read")
def get_history(patient_id):

    records = list(

        records_collection.find({

            "patientId": patient_id

        }).sort("timestamp", 1)
    )

    for r in records:

        r["_id"] = str(r["_id"])

    # =====================================
    # AUDIT LOG
    # =====================================
    log_action(

        request.user["userId"],

        request.user["role"],

        "VIEW_HISTORY",

        patient_id
    )

    return jsonify(records)

# =========================================
# CURRENT DISEASES API
# =========================================
@patient_bp.route('/current-diseases/<patient_id>', methods=['GET'])
@jwt_required
@access_required("read")
def current_diseases(patient_id):

    diseases = list(

        diseases_collection.find({

            "patientId": patient_id,

            "status": {
                "$ne": "cured"
            }
        })
    )

    for disease in diseases:

        disease["_id"] = str(
            disease["_id"]
        )

    return jsonify(
        diseases
    )

# =========================================
# SUMMARY API
# =========================================
@patient_bp.route('/summary/<patient_id>', methods=['GET'])
@jwt_required
@access_required("read")
def get_summary(patient_id):

    cured = []

    active = []

    improving = []

    diseases = list(

        diseases_collection.find({

            "patientId": patient_id
        })
    )

    for disease in diseases:

        disease["_id"] = str(
            disease["_id"]
        )

        status = disease.get(

            "status",

            ""
        ).lower()

        if status == "cured":

            cured.append(
                disease
            )

        elif status == "improving":

            improving.append(
                disease
            )

        else:

            active.append(
                disease
            )

    return jsonify({

        "active":
        active,

        "improving":
        improving,

        "cured":
        cured
    })

# =========================================
# LATEST RECORDS API
# =========================================
@patient_bp.route('/latest/<patient_id>', methods=['GET'])
@jwt_required
@access_required("read")
def latest_record(patient_id):

    latest = records_collection.find_one(

        {
            "patientId": patient_id
        },

        sort=[("timestamp", -1)]
    )

    if not latest:

        return jsonify({})

    latest["_id"] = str(latest["_id"])

    return jsonify(latest)

# =========================================
# DELETE RECORD
# =========================================
@patient_bp.route(

    '/delete-record/<record_id>',

    methods=['DELETE']
)
@jwt_required
@role_required(["patient"])
def delete_record(record_id):

    try:

        patient_id = request.user[

            "userId"
        ]

        record = records_collection.find_one({

            "recordId":

            record_id,

            "patientId":

            patient_id
        })

        if not record:

            return jsonify({

                "error":

                "Record not found"

            }), 404

        # =====================================
        # VERIFIED RECORD CANNOT DELETE
        # =====================================
        if record["status"] == "verified":

            return jsonify({

                "error":

                "Verified records cannot be deleted"

            }), 403

        # =====================================
        # ONLY pending/flagged ALLOWED
        # =====================================
        if record["status"] not in [

            "pending_verification",

            "flagged"
        ]:

            return jsonify({

                "error":

                "Record cannot be deleted"

            }), 403

        records_collection.delete_one({

            "_id":

            record["_id"]
        })

        # =====================================
        # AUDIT LOG
        # =====================================
        log_action(

            request.user["userId"],

            request.user["role"],

            "DELETE_RECORD",

            patient_id
        )

        return jsonify({

            "message":

            "Record deleted successfully"
        })

    except Exception as e:

        return jsonify({

            "error":

            str(e)
        }), 500
    
# =========================================
# GET PATIENT RECORDS
# =========================================
@patient_bp.route(

    '/records/<patient_id>',

    methods=['GET']
)
@jwt_required
@access_required("read")
def get_records(patient_id):

    try:

        records = list(

            records_collection.find({

                "patientId":

                patient_id,

                "isArchived":

                False
            })

            .sort(

                "uploadedAt",

                -1
            )
        )

        for r in records:

            r["_id"] = str(

                r["_id"]
            )

        return jsonify(

            records
        )

    except Exception as e:

        return jsonify({

            "error":

            str(e)
        }), 500
    
# =========================================
# PATIENT STATS
# =========================================
@patient_bp.route(
    '/patient-stats',
    methods=['GET']
)
@jwt_required
@role_required(["patient"])
def patient_stats():

    try:

        patient_id = request.user[
            "userId"
        ]

        hospital_visits = (

            visits_collection.count_documents({

                "patientId":
                patient_id
            })
        )

        total_reports = (

            records_collection.count_documents({

                "patientId":
                patient_id,

                "isArchived":
                False
            })
        )

        doctors_treated = len(

            visits_collection.distinct(

                "doctorId",

                {
                    "patientId":
                    patient_id
                }
            )
        )

        active_diseases = diseases_collection.count_documents({

            "patientId": patient_id,

            "status": {
                "$ne": "cured"
            }
        })

        return jsonify({

            "doctorsTreated":
            doctors_treated,

            "totalReports":
            total_reports,

            "hospitalVisits":
            hospital_visits,

            "activeDiseases":
            active_diseases
        })

    except Exception as e:

        return jsonify({

            "error":
            str(e)
        }), 500
    
# =========================================
# PATIENT ACCESS
# =========================================
@patient_bp.route(
    '/patient-access',
    methods=['GET']
)
@jwt_required
@role_required(["patient"])
def patient_access():

    try:

        patient_id = request.user[
            "userId"
        ]

        current_access = list(

            access_collection.find({

                "patientId":
                patient_id,

                "$or": [

                    {
                        "canRead": True
                    },

                    {
                        "canUpdate": True
                    }
                ]
            })

            .sort(
                "expiryTime",
                -1
            )
        )

        requests = []

        for access in current_access:

            access["_id"] = str(
                access["_id"]
            )

        return jsonify({

            "currentAccess":
            current_access,

            "requests":
            requests
        })

    except Exception as e:

        return jsonify({

            "error":
            str(e)
        }), 500
    
# =========================================
# DISEASE TIMELINE
# =========================================
@patient_bp.route(
    '/disease-timeline',
    methods=['GET']
)
@jwt_required
@role_required(["patient"])
def disease_timeline():

    try:

        patient_id = request.user[
            "userId"
        ]

        diseases = list(

            diseases_collection.find({

                "patientId":
                patient_id,

                "status": {
                    "$ne": "cured"
                }
            })

            .sort(
                "diagnosedAt",
                -1
            )
        )

        for disease in diseases:

            disease["_id"] = str(
                disease["_id"]
            )

        return jsonify(
            diseases
        )

    except Exception as e:

        return jsonify({

            "error":
            str(e)
        }), 500

# =========================================
# MY VISITS
# =========================================
@patient_bp.route(
    '/my-visits',
    methods=['GET']
)
@jwt_required
@role_required(["patient"])
def my_visits():

    try:

        patient_id = request.user[
            "userId"
        ]

        visits = list(

            visits_collection.find({

                "patientId":
                patient_id
            })

            .sort(
                "createdAt",
                -1
            )
        )

        for visit in visits:

            visit["_id"] = str(
                visit["_id"]
            )

        return jsonify(
            visits
        )

    except Exception as e:

        return jsonify({

            "error":
            str(e)
        }), 500
    
# =========================================
# MY DOCTORS
# =========================================
@patient_bp.route(
    '/my-doctors',
    methods=['GET']
)
@jwt_required
@role_required(["patient"])
def my_doctors():

    try:

        patient_id = request.user[
            "userId"
        ]

        doctor_ids = visits_collection.distinct(

            "doctorId",

            {
                "patientId":
                patient_id
            }
        )

        doctors = []

        for doctor_id in doctor_ids:

            doctor = users_collection.find_one(

                {
                    "userId":
                    doctor_id,

                    "role":
                    "doctor"
                },

                {
                    "_id": 0,
                    "password": 0
                }
            )

            if doctor:

                doctors.append(
                    doctor
                )

        return jsonify(
            doctors
        )

    except Exception as e:

        return jsonify({

            "error":
            str(e)
        }), 500