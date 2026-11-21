from flask import Blueprint, jsonify

from middleware.auth_middleware import jwt_required

from db import doctor_profiles_collection

doctor_profile_bp = Blueprint(
    "doctor_profile",
    __name__
)

@doctor_profile_bp.route(
    "/doctor-profile/<doctor_id>",
    methods=["GET"]
)
@jwt_required
def get_doctor_profile(
    doctor_id
):

    profile = (
        doctor_profiles_collection.find_one(
            {
                "doctorId":
                doctor_id
            },
            {
                "_id": 0
            }
        )
    )

    if not profile:

        return jsonify({
            "error":
            "Doctor profile not found"
        }), 404

    return jsonify(profile)