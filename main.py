import os
from dotenv import load_dotenv
basedir=os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir,'.env'))
import uuid
import datetime
import sqlite3
import json
import requests
from flask import Flask, request                 
from twilio.twiml.messaging_response import MessagingResponse 
from ibm_watson_machine_learning.foundation_models import Model
from ibm_watson import SpeechToTextV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

# --- Credentials ---
# (All your .env variables are loaded here)
API_KEY = os.getenv("API_KEY")
PROJECT_ID = os.getenv("PROJECT_ID")
URL = os.getenv("WML_URL")
STT_API_KEY = os.getenv("STT_API_KEY")
STT_URL = os.getenv("STT_URL")


# --- Initialize Flask App --- 
app = Flask(__name__)

# --- NEW: Conversation State Management ---
# This dictionary will hold the state of conversations that are awaiting more info.
# Key: user's phone number, Value: a dictionary with the state and partial ticket data.
conversation_state = {}

# --- Database Functions ---
# (These remain the same as before)
def setup_database():
    conn = sqlite3.connect('grievances.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL UNIQUE,
            timestamp TEXT NOT NULL,
            complaint TEXT NOT NULL,
            category TEXT,
            location TEXT,
            urgency TEXT,
            summary TEXT,
            status TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def save_ticket(ticket_data, status="New"):
    conn = sqlite3.connect('grievances.db')
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO tickets 
           (ticket_id, timestamp, complaint, category, location, urgency, summary, status) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticket_data['ticket_id'], ticket_data['timestamp'], ticket_data['complaint'],
            ticket_data['category'], ticket_data['location'], ticket_data['urgency'],
            ticket_data['summary'], status
        )
    )
    conn.commit()
    conn.close()
    print(f"--- ✅ Ticket {ticket_data['ticket_id']} saved to database. ---")

def get_ticket_status(ticket_id):
    conn = sqlite3.connect('grievances.db')
    cursor = conn.cursor()
    cursor.execute("SELECT status, summary FROM tickets WHERE ticket_id = ?", (ticket_id.upper(),))
    result = cursor.fetchone()
    conn.close()
    return result

# --- Initialize AI Services ---
ai_model = None
speech_to_text = None
print("--- Initializing AI Services... ---")

try:
    credentials = {"url": URL, "apikey": API_KEY}

    ai_model = Model(
        model_id="meta-llama/llama-3-2-3b-instruct",
        params={"max_new_tokens": 300, "repetition_penalty": 1.05},
        credentials=credentials,
        project_id=PROJECT_ID
    )
    stt_authenticator = IAMAuthenticator(STT_API_KEY)
    speech_to_text = SpeechToTextV1(authenticator=stt_authenticator)
    speech_to_text.set_service_url(STT_URL)
    print("--- ✅ AI Services are ready. ---")
except Exception as e:
    print(f"--- ❌ FAILED to initialize AI services: {e} ---")


@app.route('/whatsapp', methods=['POST'])
def whatsapp_listener():
    if not ai_model or not speech_to_text:
        return "AI Services not initialized", 500

    user_message = ""
    sender_phone = request.form.get('From', '')

    # --- MODIFIED: Handle Conversational State FIRST ---
    if sender_phone in conversation_state:
        state = conversation_state[sender_phone]
        # If we are waiting for a location...
        if state.get('awaiting') == 'location':
            print(f"--- Received location for ongoing ticket ---")
            location_message = request.form.get('Body', '').strip()
            ticket_data = state['ticket_data']
            ticket_data['location'] = location_message # Update the location
            
            # Now we have all the info, so we save the ticket and reply
            save_ticket(ticket_data)
            reply_message = (
                f"Thank you for providing the location. Your ticket *{ticket_data['ticket_id']}* has been fully registered.\n\n"
                f" *Category:* {ticket_data['category']}\n"
                f" *Location:* {ticket_data['location']}\n"
                f" *Summary:* {ticket_data['summary']}"
            )
            # Clear the state for this user
            del conversation_state[sender_phone]
            
            response = MessagingResponse()
            response.message(reply_message)
            return str(response)

    # --- If not in a state, proceed with normal logic ---
    if int(request.form.get('NumMedia', 0)) > 0:
        # (Voice note transcription logic remains the same)
        try:
            audio_url = request.form['MediaUrl0']
            audio_content = requests.get(audio_url).content
            stt_response = speech_to_text.recognize(audio=audio_content, content_type=request.form['MediaContentType0']).get_result()
            user_message = stt_response['results'][0]['alternatives'][0]['transcript']
        except Exception:
            user_message = ""
    else:
        user_message = request.form.get('Body', '').strip()
    
    if not user_message:
        return str(MessagingResponse().message("Sorry, I couldn't understand that. Please try again."))

   
    try:
        # --- NEW: Simplified Intent Detection ---
        intent_prompt = f"""
        Analyze this message and respond with a single word: is the user's primary intent "new_complaint" or "status_check"?
        Message: "{user_message}"
        """
        intent = ai_model.generate_text(prompt=intent_prompt).strip().lower()
        print(f"--- Detected intent: {intent} ---")
        if "status_check" in intent:
            # --- NEW: Dedicated Ticket ID Extraction ---
            ticket_id_extraction_prompt = f"""
            Extract the 8-character alphanumeric ticket ID from this message. Respond with only the ticket ID.
            Message: "{user_message}"
            """
            ticket_id = ai_model.generate_text(prompt=ticket_id_extraction_prompt).strip()
            
            ticket_info = get_ticket_status(ticket_id) if ticket_id else None
            if ticket_info:
                reply_message = f"Ticket *{ticket_id.upper()}* is for: '{ticket_info[1]}'.\nThe current status is: *{ticket_info[0]}*."
            else:
                reply_message = "It looks like you're asking for a status, but I couldn't find a valid ticket ID in your message."

        elif "new_complaint" in intent:
            # This logic remains the same as before
            extraction_prompt = f"""
            Analyze the complaint. Your entire response must be a single, valid JSON object.
            Complaint: "{user_message}"
            Example Response: {{"category": "Garbage", "location": "near Patna Museum", "urgency": "High", "summary": "Garbage has not been collected."}}
            """
            ai_response_text = ai_model.generate_text(prompt=extraction_prompt).strip()
            extracted_data = json.loads(ai_response_text) # Assuming this works now

            if extracted_data.get('location') == 'Not specified':
                # ... (logic for asking for clarification) ...
                reply_message = "I understand you're reporting an issue. To proceed, could you please reply with the specific location or a nearby landmark?"

            else:
                # Our Python code generates the ticket ID here
                ticket_id = str(uuid.uuid4().hex)[:8].upper()
                ticket_data = {**extracted_data, 'ticket_id': ticket_id, 'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p"), 'complaint': user_message}
                save_ticket(ticket_data)
                reply_message = (
                    f"Thank you. Your new ticket *{ticket_data['ticket_id']}* has been registered.\n\n"
                    f" *Category:* {ticket_data['category']}\n"
                    f" *Location:* {ticket_data['location']}\n"
                    f" *Summary:* {ticket_data['summary']}"
                )
        else:
            reply_message = "I'm sorry, I can only help with filing new complaints or checking the status of existing ones."

    except Exception as e:
        print(f"--- ❌ An error occurred in the main logic: {e} ---")
        reply_message = "I'm sorry, an unexpected error occurred. Please try again later."
    response = MessagingResponse()
    response.message(reply_message)
    return str(response)

if __name__ == "__main__":
    setup_database()
    app.run(debug=True,use_reloader=False)