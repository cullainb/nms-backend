from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import csv
import io
import os, json
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from google.cloud.firestore_v1.base_query import FieldFilter

# create flask app and enable cors
app = Flask(__name__)
CORS(app)

# --------------------------
# initialize firestore
# --------------------------
cred_dict = json.loads(os.environ["FIREBASE_KEY_JSON"])
cred = credentials.Certificate(cred_dict)
initialize_app(cred)
db = firestore.client()

# ==========================
# doctor stuff
# ==========================

@app.route("/doctors", methods=["POST"])
def add_doctor():
    data = request.json
    doc_id = f"dr{data['last_name'].capitalize()}"
    doctor_data = {
        "firstName": data["first_name"],
        "lastName": data["last_name"],
        "email": data["email"],
        "address": data["address"],
        "phone": data["phone"]
    }
    db.collection("doctors").document(doc_id).set(doctor_data)
    return jsonify({"message": "doctor added", "id": doc_id}), 201


@app.route("/doctors", methods=["GET"])
def get_all_doctors():
    docs = db.collection("doctors").stream()
    doctors = {doc.id: doc.to_dict() for doc in docs}
    return jsonify(doctors), 200


@app.route("/doctors/<doctor_id>", methods=["GET"])
def get_doctor(doctor_id):
    doc = db.collection("doctors").document(doctor_id).get()
    if doc.exists:
        return jsonify(doc.to_dict()), 200
    return jsonify({"error": "doctor not found"}), 404


@app.route("/doctors/by_email", methods=["POST"])
def get_doctor_by_email():
    data = request.json

    if not data or "email" not in data:
        return jsonify({"error": "Email is required"}), 400

    email = data["email"]

    docs = (
        db.collection("doctors")
        .where(filter=FieldFilter("email", "==", email))
        .limit(1)
        .stream()
    )

    for doc in docs:
        return jsonify({
            "id": doc.id,
            **doc.to_dict()
        })

    return jsonify({"error": "Doctor not found"}), 404

@app.route("/doctors/<doctor_id>", methods=["DELETE"])
def delete_doctor(doctor_id):
    doctor_ref = db.collection("doctors").document(doctor_id)
    doc = doctor_ref.get()

    if not doc.exists:
        return jsonify({"error": "Doctor not found"}), 404

    doctor_ref.delete()

    return jsonify({
        "message": "Doctor deleted",
        "id": doctor_id
    })

@app.route("/doctors/<doctor_id>", methods=["PUT"])
def edit_doctor(doctor_id):
    doctor_ref = db.collection("doctors").document(doctor_id)
    doc = doctor_ref.get()

    if not doc.exists:
        return jsonify({"error": "Doctor not found"}), 404

    data = request.json

    allowed_fields = ["firstName", "lastName", "email", "address", "phone"]

    update_data = {
        field: value
        for field, value in data.items()
        if field in allowed_fields
    }

    if not update_data:
        return jsonify({"error": "No valid fields provided"}), 400

    doctor_ref.update(update_data)

    return jsonify({
        "message": "Doctor updated",
        "id": doctor_id,
        "updatedFields": list(update_data.keys())
    })


# ==========================
# patient stuff
# ==========================

@app.route("/patients", methods=["POST"])
def add_patient():
    data = request.json
    doc_id = f"{data['first_name'].capitalize()}{data['last_name'].capitalize()}"
    patient_data = {
        "firstName": data["first_name"],
        "lastName": data["last_name"],
        "age": data["age"],
        "gender": data["gender"],
        "doctorId": db.document(f"doctors/{data['doctor_id']}"),
        "notes": data.get("notes", ""),
        "createdAt": firestore.SERVER_TIMESTAMP
    }
    db.collection("patients").document(doc_id).set(patient_data)
    return jsonify({"message": "patient added", "id": doc_id}), 201


@app.route("/patients/<patient_id>", methods=["GET"])
def get_patient(patient_id):
    doc = db.collection("patients").document(patient_id).get()
    if not doc.exists:
        return jsonify({"error": "patient not found"}), 404
    data = doc.to_dict()
    # convert firestore references to string so json works
    if "doctorId" in data and isinstance(data["doctorId"], firestore.DocumentReference):
        data["doctorId"] = data["doctorId"].id
    return jsonify(data), 200


@app.route("/patients/by_doctor/<doctor_id>", methods=["GET"])
def get_patients_by_doctor(doctor_id):
    doctor_ref = db.document(f"doctors/{doctor_id}")
    docs = db.collection("patients").where(
        filter=FieldFilter("doctorId", "==", doctor_ref)
    ).stream()
    patients = {}
    for doc in docs:
        data = doc.to_dict()
        if "doctorId" in data and isinstance(data["doctorId"], firestore.DocumentReference):
            data["doctorId"] = data["doctorId"].id
        patients[doc.id] = data
    return jsonify(patients), 200


@app.route("/patients/<patient_id>/mark_paid", methods=["POST"])
def mark_patient_paid(patient_id):
    patient_ref = db.collection("patients").document(patient_id)
    doc = patient_ref.get()

    if not doc.exists:
        return jsonify({"error": "Patient not found"}), 404

    patient_data = doc.to_dict()

    # checks if user has paid
    if patient_data.get("paid") is True:
        return jsonify({
            "message": "Patient already paid",
            "patientId": patient_id
        })

    # set paid to true
    patient_ref.update({
        "paid": True,
        "paidAt": firestore.SERVER_TIMESTAMP
    })

    return jsonify({
        "message": "Patient successfully paid",
        "patientId": patient_id
    })


@app.route("/patients/<patient_id>/paid_status", methods=["GET"])
def get_patient_paid_status(patient_id):
    patient_ref = db.collection("patients").document(patient_id)
    doc = patient_ref.get()

    if not doc.exists:
        return jsonify({"error": "Patient not found"}), 404

    patient_data = doc.to_dict()

    # default to false
    paid_status = patient_data.get("paid", False)

    return jsonify({
        "patientId": patient_id,
        "paid": paid_status
    })


@app.route("/patients/<patient_id>", methods=["DELETE"])
def delete_patient(patient_id):
    patient_ref = db.collection("patients").document(patient_id)
    doc = patient_ref.get()

    if not doc.exists:
        return jsonify({"error": "Patient not found"}), 404

    # delete patients risk scores as well
    risk_scores = patient_ref.collection("riskScores").stream()
    for score in risk_scores:
        score.reference.delete()

    patient_ref.delete()

    return jsonify({
        "message": "Patient deleted",
        "id": patient_id
    })

@app.route("/patients/<patient_id>", methods=["PUT"])
def edit_patient(patient_id):
    patient_ref = db.collection("patients").document(patient_id)
    doc = patient_ref.get()

    if not doc.exists:
        return jsonify({"error": "Patient not found"}), 404

    data = request.json

    allowed_fields = ["firstName", "lastName", "age", "gender", "notes"]

    update_data = {
        field: value
        for field, value in data.items()
        if field in allowed_fields
    }

    # Handle doctor reassignment if provided
    if "doctor_id" in data:
        update_data["doctorId"] = db.document(f"doctors/{data['doctor_id']}")

    if not update_data:
        return jsonify({"error": "No valid fields provided"}), 400

    patient_ref.update(update_data)

    return jsonify({
        "message": "Patient updated",
        "id": patient_id,
        "updatedFields": list(update_data.keys())
    })



# ==========================
# report stuff
# ==========================

@app.route("/reports", methods=["POST"])
def add_report():
    data = request.json
    patient_id = f"{data['patient_first'].capitalize()}{data['patient_last'].capitalize()}"
    doc_id = f"{patient_id}{data['report_type'].upper()}"
    report_data = {
        "patientId": db.document(f"patients/{patient_id}"),
        "reportType": data["report_type"].upper(),
        "dateOfReport": firestore.SERVER_TIMESTAMP,
        "notes": data.get("notes", "")
    }
    db.collection("reports").document(doc_id).set(report_data)
    return jsonify({"message": "report added", "id": doc_id}), 201


@app.route("/reports/<report_id>", methods=["GET"])
def get_report(report_id):
    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        return jsonify({"error": "report not found"}), 404
    data = doc.to_dict()
    # convert patientId reference to string
    if "patientId" in data and isinstance(data["patientId"], firestore.DocumentReference):
        data["patientId"] = data["patientId"].id
    return jsonify(data), 200


@app.route("/reports/by_patient/<first>/<last>", methods=["GET"])
def get_reports_by_patient(first, last):
    patient_id = f"{first.capitalize()}{last.capitalize()}"
    patient_ref = db.document(f"patients/{patient_id}")
    docs = db.collection("reports").where(
        filter=FieldFilter("patientId", "==", patient_ref)
    ).stream()
    reports = {}
    for doc in docs:
        data = doc.to_dict()
        if "patientId" in data and isinstance(data["patientId"], firestore.DocumentReference):
            data["patientId"] = data["patientId"].id
        reports[doc.id] = data
    return jsonify(reports), 200

# ==========================
# account stuff
# ==========================

def addAccount(email: str, password: str, role: str):
    if role not in ["doctor", "patient", "admin"]:
        return {"success": False, "error": "role must be doctor, patient or admin"}
    existing = db.collection("accounts").where("email", "==", email).limit(1).get()
    if existing:
        return {"success": False, "error": "account already exists"}
    account_data = {"email": email, "password": password, "role": role}
    doc_ref = db.collection("accounts").add(account_data)
    return {"success": True, "id": doc_ref[1].id}


def checkValidAccount(email: str, password: str):
    docs = db.collection("accounts").where("email", "==", email).limit(1).get()
    if not docs:
        return {"valid": False, "error": "invalid credentials"}
    account = docs[0].to_dict()
    if password != account["password"]:
        return {"valid": False, "error": "invalid credentials"}
    return {"valid": True, "role": account["role"]}


@app.route("/accounts", methods=["POST"])
def create_account():
    data = request.json
    result = addAccount(data["email"], data["password"], data["role"])
    return jsonify(result)


@app.route("/accounts/login", methods=["POST"])
def login_account():
    data = request.json
    result = checkValidAccount(data["email"], data["password"])
    return jsonify(result)

# ==========================
# risk score stuff
# ==========================

@app.route("/patients/<patient_id>/riskScores", methods=["POST"])
def add_risk_score(patient_id):
    patient_ref = db.collection("patients").document(patient_id)
    patient_doc = patient_ref.get()
    if not patient_doc.exists:
        return jsonify({"error": "patient not found"}), 404

    data = request.json

    # extract new fields
    risk_score_data = {
        "riskScore": data["riskScore"],            # number
        "riskLevel": data["riskLevel"],            # string
        "familyHistory": data["familyHistory"],    # string
        "assessmentDate": data["assessmentDate"],  # timestamp string from client
        "createdAt": firestore.SERVER_TIMESTAMP    # auto timestamp
    }

    scores_ref = patient_ref.collection("riskScores")
    docs = scores_ref.stream()
    existing_numbers = [int(doc.id) for doc in docs if doc.id.isdigit()]
    next_id = max(existing_numbers) + 1 if existing_numbers else 1

    scores_ref.document(str(next_id)).set(risk_score_data)

    return jsonify({
        "message": "risk score added",
        "patientId": patient_id,
        "riskScoreId": str(next_id)
    }), 201


@app.route("/patients/<patient_id>/riskScores/latest", methods=["GET"])
def get_latest_risk_score(patient_id):
    patient_ref = db.collection("patients").document(patient_id)
    patient_doc = patient_ref.get()
    if not patient_doc.exists:
        return jsonify({"error": "patient not found"}), 404

    scores_ref = patient_ref.collection("riskScores")
    docs = scores_ref.stream()

    latest_score = None
    max_id = -1

    for doc in docs:
        try:
            doc_id = int(doc.id)
        except ValueError:
            continue

        if doc_id > max_id:
            max_id = doc_id
            latest_score = doc.to_dict()

    if not latest_score:
        return jsonify({"error": "no risk scores found"}), 404

    return jsonify({
        "patientId": patient_id,
        "riskScoreId": str(max_id),
        "data": latest_score
    }), 200


# ==========================
# support ticket stuff
# ==========================

@app.route("/supportTickets", methods=["POST"])
def create_support_ticket():
    data = request.json

    if not data or "supportIssue" not in data:
        return jsonify({"error": "Support message is required"}), 400

    ticket_data = {
        "supportIssue": data["supportIssue"]
    }

    doc_ref = db.collection("supportTickets").add(ticket_data)

    return jsonify({
        "message": "Support ticket created",
        "ticketId": doc_ref[1].id
    }), 201


@app.route("/supportTickets", methods=["GET"])
def get_all_support_tickets():
    docs = db.collection("supportTickets").stream()

    tickets = {
        doc.id: doc.to_dict()
        for doc in docs
    }

    return jsonify(tickets)

@app.route("/supportTickets/<ticket_id>", methods=["DELETE"])
def delete_support_ticket(ticket_id):
    ticket_ref = db.collection("supportTickets").document(ticket_id)
    doc = ticket_ref.get()

    if not doc.exists:
        return jsonify({"error": "Support ticket not found"}), 404

    ticket_ref.delete()

    return jsonify({
        "message": "Support ticket deleted",
        "ticketId": ticket_id
    })

# ==========================
# review stuff
# ==========================

@app.route("/reviews", methods=["POST"])
def create_review():
    data = request.json

    if not data or "rating" not in data or "review" not in data:
        return jsonify({"error": "rating and review fields are required"}), 400

    # validation
    if not isinstance(data["rating"], (int, float)):
        return jsonify({"error": "rating must be a number"}), 400

    if rating < 1 or rating > 5:
        return jsonify({"error": "rating must be between 1 and 5"}), 400

    review_data = {
        "rating": data["rating"],
        "review": data["review"]
    }

    doc_ref = db.collection("reviews").add(review_data)

    return jsonify({
        "message": "Review created",
        "reviewId": doc_ref[1].id
    }), 201

@app.route("/reviews", methods=["GET"])
def get_all_reviews():
    docs = db.collection("reviews").stream()

    reviews = {
        doc.id: doc.to_dict()
        for doc in docs
    }

    return jsonify(reviews)

@app.route("/reviews/<review_id>", methods=["DELETE"])
def delete_review(review_id):
    review_ref = db.collection("reviews").document(review_id)
    doc = review_ref.get()

    if not doc.exists:
        return jsonify({"error": "Review not found"}), 404

    review_ref.delete()

    return jsonify({
        "message": "Review deleted",
        "reviewId": review_id
    })

# ==========================
# export patient data by doctor ID
# ==========================

@app.route("/export/doctors/<doctor_id>/patients", methods=["GET"])
def export_doctor_patients(doctor_id):
    doctor_ref = db.document(f"doctors/{doctor_id}")

    # doctor exists
    if not doctor_ref.get().exists:
        return jsonify({"error": "Doctor not found"}), 404

    # get all patients for this doctor
    patients = db.collection("patients").where(
        filter=FieldFilter("doctorId", "==", doctor_ref)
    ).stream()

    output = io.StringIO()
    writer = csv.writer(output)

    # header
    writer.writerow([
        "doctorId",
        "patientId",
        "firstName",
        "lastName",
        "age",
        "gender",
        "riskScoreId",
        "riskScore",
        "riskLevel",
        "familyHistory",
        "lastAssessmentDate",
        "createdAt"
    ])

    for patient in patients:
        patient_data = patient.to_dict()
        patient_id = patient.id

        risk_scores_ref = (
            db.collection("patients")
            .document(patient_id)
            .collection("riskScores")
        )

        risk_scores = risk_scores_ref.stream()

        for score in risk_scores:
            score_data = score.to_dict()

            writer.writerow([
                doctor_id,
                patient_id,
                patient_data.get("firstName"),
                patient_data.get("lastName"),
                patient_data.get("age"),
                patient_data.get("gender"),
                score.id,
                score_data.get("riskScore"),
                score_data.get("riskLevel"),
                score_data.get("familyHistory"),
                score_data.get("lastAssessmentDate"),
                score_data.get("createdAt")
            ])

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={doctor_id}_patients_export.csv"
        }
    )


# ==========================
# homepage route
# ==========================

@app.route("/", methods=["GET"])
def index():
    return "firestore flask api is running!"

# ==========================
# run the app
# ==========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)











