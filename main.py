import os
from ibm_watson_machine_learning.foundation_models import Model


 

def main():
    """The main function to run our command-line AI agent."""
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

        # --- Main Application Loop ---
        while True:
            # Get input from the user
            user_input = input("You: ")
            
            # Check if the user wants to quit
            if user_input.lower() in ["exit", "quit"]:
                print("Agent: Goodbye!")
                break
            
            # --- Generate AI Response ---
            prompt = f"You are a helpful municipal grievance agent. First, categorize the following citizen complaint into one of these categories: Road Maintenance, Garbage, Streetlight, or Water Supply. Then, in a friendly tone, confirm that a ticket has been created. Complaint: '{user_input}'"
            
            print("Agent: ...thinking...")
            ai_response = model.generate_text(prompt=prompt)
            print(f"Agent: {ai_response}")

    except Exception as e:
        print(f"--- ❌ FAILED: An error occurred during initialization ---")
        print(e)

# Run the main function when the script is executed
if __name__ == "__main__":
    main()
