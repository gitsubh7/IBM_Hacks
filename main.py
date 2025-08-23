import os
import uuid
import datetime
import sqlite3
from flask import Flask, request                 
from twilio.twiml.messaging_response import MessagingResponse 
from ibm_watson_machine_learning.foundation_models import Model
from dotenv import load_dotenv
load_dotenv()

# --- Credentials ---
API_KEY = os.getenv("API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")
URL = os.getenv("WML_URL")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# --- Initialize Flask App --- 
app = Flask(__name__)

# --- Database Functions ---
def setup_database():
    """Creates the database and the tickets table if they don't exist."""
    conn = sqlite3.connect('grievances.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            complaint TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_ticket(ticket_id, timestamp, complaint, category, status="New"):
    """Saves a new ticket to the database."""
    conn = sqlite3.connect('grievances.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tickets (ticket_id, timestamp, complaint, category, status) VALUES (?, ?, ?, ?, ?)",
        (ticket_id, timestamp, complaint, category, status)
    )
    conn.commit()
    conn.close()
    print(f"--- ✅ Ticket {ticket_id} saved to database. ---")

# --- Initialize AI Model ---
# We do this once when the server starts
print("--- Initializing AI Agent... ---")
try:
    credentials = {"url": URL, "apikey": API_KEY}
    ai_model = Model(
        model_id="ibm/granite-3-3-8b-instruct",
        params={"max_new_tokens": 200, "repetition_penalty": 1.05},
        credentials=credentials,
        project_id=PROJECT_ID
    )
    print("--- ✅ AI Agent is ready. ---")
except Exception as e:
    print(f"--- ❌ FAILED to initialize AI model: {e} ---")
    ai_model = None


@app.route('/whatsapp', methods=['POST'])
def whatsapp_listener():
    """Listens for incoming WhatsApp messages and processes them."""
    if not ai_model:
        return "AI Model not initialized", 500

    # 1. Get the user's message
    user_complaint = request.form.get('Body', '').strip()
    sender_phone = request.form.get('From', '')
    print(f"\n--- New Message from {sender_phone} ---")
    print(f"User: {user_complaint}")

    # 2. Generate Ticket ID and Timestamp
    ticket_id = str(uuid.uuid4().hex)[:8].upper()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
    
    # 3. Use the AI to categorize the complaint
    prompt = f"Analyze the complaint: '{user_complaint}'. Classify it into one of these categories: Road Maintenance, Garbage, Streetlight, or Water Supply. Respond with only the category name."
    print("Agent: ...thinking...")
    ai_category = ai_model.generate_text(prompt=prompt).strip()

    # 4. Save the ticket to our database
    save_ticket(ticket_id, timestamp, user_complaint, ai_category)
    
    # 5. Create the reply message for WhatsApp
    reply_message = (
        f"Thank you for your report. Your ticket *{ticket_id}* has been registered "
        f"under the category: *{ai_category}*. "
        "We will address it shortly."
    )
    
    print(f"Agent: Thank you for your report. We have successfully registered ticket number {ticket_id} under the '{ai_category}' category.")
    
    # 6. Send the reply via WhatsApp
    response = MessagingResponse()
    response.message(reply_message)
    
    return str(response)

if __name__ == "__main__":
    setup_database()
    app.run(debug=True) 