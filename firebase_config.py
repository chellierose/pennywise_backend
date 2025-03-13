import firebase_admin
from firebase_admin import credentials, auth, firestore

# Load Firebase credentials
cred = credentials.Certificate("PennyWise.json")
firebase_admin.initialize_app(cred)

# Firestore database instance
db = firestore.client()
