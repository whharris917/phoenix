import json
import os
import time
import subprocess
import sys
import threading
import socketio

# --- Configuration ---
OUTPUT_DIR = "sdlc/trace_maps"
APP_URL = "http://localhost:5001"

# --- Scenario Definitions ---
SCENARIOS = {
    "01_startup_and_connect": {
        "description": "Traces the initial connection of a client, session creation, and disconnection without any prompts.",
        "steps": [] # Connection is handled by the runner itself
    },
    "02_simple_prompt_no_tools": {
        "description": "Traces a simple user prompt that the agent can answer without using any tools.",
        "steps": [
            {"action": "run_prompt", "prompt": "What is the capital of Poland?"}
        ]
    },
    "03_complex_prompt_with_tools": {
        "description": "Traces a complex prompt that requires the agent to use tools (in this case, listing files).",
        "steps": [
            {"action": "run_prompt", "prompt": "Please list the files in the current directory."}
        ]
    }
}

class ScenarioRunner:
    """
    An E2E test runner that starts the application, connects as a real client,
    runs a single scenario, and captures its trace log.
    """
    def __init__(self):
        self.sio = socketio.Client()
        self.task_complete_event = threading.Event()
        self.trace_log = None
        self.setup_client_handlers()

    def setup_client_handlers(self):
        """Defines the event handlers for our Socket.IO client."""
        @self.sio.event
        def connect():
            print("Client: Successfully connected to the server.")

        @self.sio.event
        def disconnect():
            print("Client: Disconnected from the server.")

        @self.sio.on('log_message')
        def on_log_message(data):
            # We consider the task complete when the agent gives a final answer.
            if data.get("type") == "final_answer":
                print(f"Client: Received final answer. Task complete.")
                self.task_complete_event.set()
        
        @self.sio.on('tool_log')
        def on_tool_log(data):
             # A tool result also signifies the end of a reasoning loop iteration.
             print(f"Client: Received tool log. Task step complete.")
             self.task_complete_event.set()

        @self.sio.on('trace_log_response')
        def on_trace_log_response(data):
            """Receives the trace log from the server."""
            self.trace_log = data.get("trace")
            self.task_complete_event.set()

    def run_scenario(self, scenario_name, scenario_config):
        print(f"\n--- Running Scenario: {scenario_name} ---")
        self.sio.connect(APP_URL, wait_timeout=10)
        
        # 1. Reset the tracer on the server.
        self.task_complete_event.clear()
        self.sio.emit('reset_tracer')
        time.sleep(0.5) # Give a moment for the event to process

        # 2. Execute scenario steps.
        for step in scenario_config["steps"]:
            action = step["action"]
            print(f"  Client: Executing step: {action}...")
            if action == "run_prompt":
                self.task_complete_event.clear()
                self.sio.emit('start_task', {'prompt': step['prompt']})
                # Wait for the server to signal that the task is done.
                completed = self.task_complete_event.wait(timeout=30)
                if not completed:
                    print("  Client: WARNING - Task timed out.")

        # 3. Request the trace log from the server.
        self.task_complete_event.clear()
        self.trace_log = None
        self.sio.emit('get_trace_log')
        self.task_complete_event.wait(timeout=5)

        # 4. Disconnect and save the results.
        self.sio.disconnect()
        self.save_trace(scenario_name, scenario_config)
        print(f"--- Scenario Complete. ---")

    def save_trace(self, scenario_name, scenario_config):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, f"{scenario_name}.json")
        
        output_data = {
            "scenario_name": scenario_name,
            "description": scenario_config["description"],
            "trace": self.trace_log or "Trace log could not be retrieved."
        }
        
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Trace map saved to '{output_path}'")


def main():
    """
    Main function to start servers, run scenarios, and stop servers.
    """
    haven_process = None
    app_process = None
    try:
        # Start Haven
        print("Starting Haven service...")
        haven_process = subprocess.Popen([sys.executable, "haven.py"])
        time.sleep(3) # Wait for Haven to be ready

        # Start the Flask App
        print("Starting Flask App service...")
        app_process = subprocess.Popen([sys.executable, "phoenix.py"])
        time.sleep(5) # Wait for Flask app to be ready

        # **FIX: Create a new runner for each scenario to ensure a fresh connection.**
        for name, config in SCENARIOS.items():
            runner = ScenarioRunner()
            runner.run_scenario(name, config)

    finally:
        # Ensure all background processes are terminated
        if app_process:
            print("\nTerminating Flask App service...")
            app_process.terminate()
            app_process.wait()
        if haven_process:
            print("Terminating Haven service...")
            haven_process.terminate()
            haven_process.wait()
        print("All services terminated.")

if __name__ == "__main__":
    main()
