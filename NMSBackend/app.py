from flask import Flask, request, jsonify
import os, json
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

app = Flask(__name__)

# Initialize Firestore using environment variable
cred_dict = json.loads(os.environ["FIREBASE_KEY_JSON"])
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# doctor functions
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
    return jsonify({"message": "Doctor added", "id": doc_id})

@app.route("/doctors", methods=["GET"])
def get_all_doctors():
    docs = db.collection("doctors").stream()
    doctors = {doc.id: doc.to_dict() for doc in docs}
    return jsonify(doctors)

@app.route("/doctors/<doctor_id>", methods=["GET"])
def get_doctor(doctor_id):
    doc = db.collection("doctors").document(doctor_id).get()
    if doc.exists:
        return jsonify(doc.to_dict())
    else:
        return jsonify({"error": "Doctor not found"}), 404

# patient functions
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
    return jsonify({"message": "Patient added", "id": doc_id})

@app.route("/patients/<patient_id>", methods=["GET"])
def get_patient(patient_id):
    doc = db.collection("patients").document(patient_id).get()
    if doc.exists:
        return jsonify(doc.to_dict())
    else:
        return jsonify({"error": "Patient not found"}), 404

@app.route("/patients/by_doctor/<doctor_id>", methods=["GET"])
def get_patients_by_doctor(doctor_id):
    doctor_ref = db.document(f"doctors/{doctor_id}")
    docs = db.collection("patients").where(
        filter=FieldFilter("doctorId", "==", doctor_ref)
    ).stream()
    patients = {doc.id: doc.to_dict() for doc in docs}
    return jsonify(patients)

# report functions
@app.route("/reports", methods=["POST"])
def add_report():
    data = request.json
    doc_id = f"{data['patient_first'].capitalize()}{data['patient_last'].capitalize()}{data['report_type'].upper()}"
    patient_id = f"{data['patient_first'].capitalize()}{data['patient_last'].capitalize()}"
    report_data = {
        "patientId": db.document(f"patients/{patient_id}"),
        "reportType": data["report_type"].upper(),
        "dateOfReport": firestore.SERVER_TIMESTAMP,
        "notes": data.get("notes", "")
    }
    db.collection("reports").document(doc_id).set(report_data)
    return jsonify({"message": "Report added", "id": doc_id})

@app.route("/reports/<report_id>", methods=["GET"])
def get_report(report_id):
    doc = db.collection("reports").document(report_id).get()
    if doc.exists:
        return jsonify(doc.to_dict())
    else:
        return jsonify({"error": "Report not found"}), 404

@app.route("/reports/by_patient/<patient_first>/<patient_last>", methods=["GET"])
def get_reports_by_patient(patient_first, patient_last):
    patient_id = f"{patient_first.capitalize()}{patient_last.capitalize()}"
    patient_ref = db.document(f"patients/{patient_id}")
    docs = db.collection("reports").where(
        filter=FieldFilter("patientId", "==", patient_ref)
    ).stream()
    reports = {doc.id: doc.to_dict() for doc in docs}
    return jsonify(reports)


@app.route("/", methods=["GET"])
def index():
    return "Firestore Flask API is running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
