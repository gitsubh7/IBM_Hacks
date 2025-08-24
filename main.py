import os
import uuid
import datetime
import sqlite3
from ibm_watson_machine_learning.foundation_models import Model
from dotenv import load_dotenv
load_dotenv()

# --- Credentials ---
API_KEY = os.getenv("API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")
URL = os.getenv("WML_URL")

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

# --- Main Application ---
def main():
    """The main function to run our command-line AI agent."""
    setup_database() # Set up the database on startup
    print("--- Initializing AI Agent... ---")
    try:
        credentials = {"url": URL, "apikey": API_KEY}
        model = Model(
            model_id="ibm/granite-3-3-8b-instruct",
            params={"max_new_tokens": 200, "repetition_penalty": 1.05},
            credentials=credentials,
            project_id=PROJECT_ID
        )
        print("--- ✅ AI Agent is ready. Type your complaint or 'exit' to quit. ---")

        while True:
            user_input = input("You: ")
            
            if user_input.lower() in ["exit", "quit"]:
                print("Agent: Goodbye!")
                break
            
            ticket_id = str(uuid.uuid4().hex)[:8].upper()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

            prompt = f"You are an AI assistant. Analyze the complaint: '{user_input}'. Your only output should be the category: Road Maintenance, Garbage, Streetlight, or Water Supply."
            
            print("Agent: ...thinking...")
            # We get the category first
            ai_category = model.generate_text(prompt=prompt).strip()

            # Now we save the ticket with the determined category
            save_ticket(ticket_id, timestamp, user_input, ai_category)

            # Then we create the user-facing response
            print(f"Agent: Thank you for your report. We have successfully registered ticket number {ticket_id} under the '{ai_category}' category. We will address it shortly.")

    except Exception as e:
        print(f"--- ❌ FAILED: An error occurred ---")
        print(e)

if __name__ == "__main__":
    main()