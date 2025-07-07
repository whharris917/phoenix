import google.generativeai as genai
import requests
import json
import sys

# --- CONFIGURATION ---
# IMPORTANT: Paste your API key here
API_KEY = 'AIzaSyALFegx2Gslr5a-xzx1sLWFOzB1EQ0xVZY' 

# The URL of our running local agent
AGENT_URL = "http://127.0.0.1:5000/execute"

# --- MAIN LOGIC ---
def run_autonomous_task(task_input):
    """Manages the end-to-end task execution with a single API call."""
    
    # 1. Configure the Gemini API client
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.5-pro')
    except Exception as e:
        print(f"ERROR: Failed to configure Gemini API. Check your API key. Details: {e}")
        return

    # 2. Ask Gemini for the command to execute (1st and ONLY API call)
    print(f"Orchestrator: Asking Gemini how to save the number '{task_input}'...")
    prompt = f"Given the input '{task_input}', what is the JSON command for my local agent to create a file named 'number.txt' containing this input as its content? The action is 'create_file'. Only respond with the JSON object."
    
    try:
        response = model.generate_content(prompt)
        command_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        command_json = json.loads(command_text)
        print(f"Orchestrator: Received command: {command_json}")
    except Exception as e:
        print(f"ERROR: Failed to get a valid command from Gemini. Details: {e}")
        return

    # 3. Execute the command using the local agent
    print("Orchestrator: Sending command to local agent...")
    agent_response = None
    try:
        print(command_json)
        res = requests.post(AGENT_URL, json=command_json)
        res.raise_for_status() 
        agent_response = res.json()
        print(f"Orchestrator: Agent responded: {agent_response}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to communicate with the local agent. Is it running? Details: {e}")
        return
        
    # --- MODIFIED PART ---
    # 4. Generate the final report LOCALLY. No second API call needed.
    print("\n--- Final Report ---")
    if agent_response and agent_response.get('status') == 'success':
        print(f"Success! The local agent has created the file 'number.txt' with the number {task_input} inside.")
    else:
        print("The task could not be completed by the local agent.")


# --- SCRIPT EXECUTION ---
if __name__ == "__main__":
    if API_KEY == 'YOUR_API_KEY_HERE':
        print("ERROR: Please update the 'API_KEY' variable in the script with your Gemini API key.")
    elif len(sys.argv) < 2:
        print("Usage: python run_task.py <some_number>")
    else:
        user_input = sys.argv[1]
        run_autonomous_task(user_input)