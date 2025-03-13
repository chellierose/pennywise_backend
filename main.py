from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from collections import defaultdict
import sqlite3
import hashlib
import datetime
from fastapi.responses import FileResponse
from firebase_config import auth  # Import Firebase Auth

app = FastAPI()

# CORS Configurations
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://192.168.1.8:8000",
    "http://localhost:19000",
    "exp://192.168.1.8:19000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firebase Authentication Middleware
def verify_token(token: str):
    """Verifies Firebase ID token"""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.get("/protected")
def protected_route(user=Depends(verify_token)):
    """Example protected route"""
    return {"message": "Welcome to a protected route!", "user": user}

# Database Connection
def get_db_connection():
    conn = sqlite3.connect("pennywise.db")
    conn.row_factory = sqlite3.Row
    return conn

# Initialize Database
def init_db():
    conn = get_db_connection()
    with conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
                            email TEXT PRIMARY KEY,
                            password TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            description TEXT NOT NULL,
                            amount REAL NOT NULL,
                            category TEXT NOT NULL,
                            date TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS goals (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            description TEXT NOT NULL,
                            amount REAL NOT NULL,
                            progress REAL NOT NULL)''')
    conn.close()

init_db()

# Hash Password
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# Pydantic Models
class UserLogin(BaseModel):
    email: str
    password: str

class UserRegister(BaseModel):
    email: str
    password: str

class Expense(BaseModel):
    description: str
    amount: float
    category: str
    date: str

class ExpenseInDB(Expense):
    id: int

class Goal(BaseModel):
    description: str
    amount: float
    progress: float

class GoalInDB(Goal):
    id: int

@app.get("/")
async def root():
    return {"message": "Welcome to PennyWise API"}

# Register User
@app.post("/register")
async def register_user(user: UserRegister):
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_password = hash_password(user.password)
    try:
        cursor.execute("INSERT INTO users (email, password) VALUES (?, ?)", (user.email, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    conn.close()
    return {"message": "User registered successfully"}

# Login User
@app.post("/login")
async def login_user(user: UserLogin):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE email = ?", (user.email,))
    record = cursor.fetchone()
    if record and record["password"] == hash_password(user.password):
        conn.close()
        return {"message": "Login successful"}
    conn.close()
    raise HTTPException(status_code=401, detail="Invalid credentials")

# Add Expense
@app.post("/expenses/", response_model=ExpenseInDB)
async def add_expense(expense: Expense, user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ensure date is in 'YYYY-MM-DD' format
    try:
        formatted_date = datetime.datetime.strptime(expense.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    cursor.execute("INSERT INTO expenses (description, amount, category, date) VALUES (?, ?, ?, ?)", 
                   (expense.description, expense.amount, expense.category, formatted_date))
    expense_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {**expense.dict(), "id": expense_id}

# Get All Expenses (Protected)
@app.get("/expenses/", response_model=List[ExpenseInDB])
async def get_expenses(user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses ORDER BY date ASC")
    expenses = cursor.fetchall()
    conn.close()
    return [ExpenseInDB(**dict(expense)) for expense in expenses]

# Delete Expense (Protected)
@app.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: int, user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return {"message": f"Expense {expense_id} deleted successfully"}

# Get Expense Graph Data (Protected)
@app.get("/expenses/graph")
async def get_expenses_graph(user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT date, amount FROM expenses ORDER BY date ASC")
    expenses = cursor.fetchall()
    conn.close()
    expense_data = defaultdict(float)
    for expense in expenses:
        expense_data[expense["date"]] += expense["amount"]
    formatted_data = [{"date": date, "total": total} for date, total in expense_data.items()]
    return formatted_data

# Create Goal (Protected)
@app.post("/goals/", response_model=GoalInDB)
async def create_goal(goal: Goal, user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO goals (description, amount, progress) VALUES (?, ?, ?)",
        (goal.description, goal.amount, goal.progress)
    )
    
    goal_id = cursor.lastrowid  # Get last inserted ID
    conn.commit()
    conn.close()
    
    return GoalInDB(id=goal_id, description=goal.description, amount=goal.amount, progress=goal.progress)

# Get Goals (Protected)
@app.get("/goals/", response_model=List[GoalInDB])
async def get_goals(user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, description, amount, progress FROM goals")  # Explicit column selection
    goals = cursor.fetchall()
    conn.close()

    return [
        GoalInDB(id=row["id"], description=row["description"], amount=row["amount"], progress=row["progress"])
        for row in goals
    ]

# Update Goal (Protected)
@app.patch("/goals/{goal_id}", response_model=GoalInDB)
async def update_goal(goal_id: int, goal: Goal, user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()

    # Retrieve existing goal
    cursor.execute("SELECT * FROM goals WHERE id = ?", (goal_id,))
    existing_goal = cursor.fetchone()
    if not existing_goal:
        conn.close()
        raise HTTPException(status_code=404, detail="Goal not found")

    # Use existing values if the new request has missing fields
    updated_description = goal.description if goal.description else existing_goal["description"]
    updated_amount = goal.amount if goal.amount else existing_goal["amount"]
    updated_progress = goal.progress if goal.progress is not None else existing_goal["progress"]

    cursor.execute(
        "UPDATE goals SET description = ?, amount = ?, progress = ? WHERE id = ?",
        (updated_description, updated_amount, updated_progress, goal_id)
    )

    conn.commit()
    conn.close()

    return GoalInDB(id=goal_id, description=updated_description, amount=updated_amount, progress=updated_progress)

# Delete Goal (Protected)
@app.delete("/goals/{goal_id}")
async def delete_goal(goal_id: int, user=Depends(verify_token)):  # Protect this route
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Goal not found")

    conn.commit()
    conn.close()
    
    return {"message": "Goal deleted successfully"}
