import json
import os
import time
import subprocess
import sys
import threading
import socketio
from typing import List, Dict, Any

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

def _get_participants_from_trace(trace_log: List[Dict[str, Any]]) -> List[str]:
    """Recursively finds all unique module participants in a trace log."""
    participants = set()
    for entry in trace_log:
        if entry.get("type") == "EVENT":
            continue
        
        module = entry.get("function", "").split('.')[0]
        if module:
            participants.add(module)
        
        if "nested_calls" in entry:
            participants.update(_get_participants_from_trace(entry["nested_calls"]))
    return sorted(list(participants))

def _generate_mermaid_lines(trace_log: List[Dict[str, Any]], from_participant: str) -> List[str]:
    """Recursively traverses the trace and generates Mermaid syntax lines."""
    lines = []
    for entry in trace_log:
        if entry.get("type") == "EVENT":
            lines.append(f"    note over {from_participant}: {entry.get('event_name', 'Unnamed Event')}")
            continue

        full_func_name = entry.get("function", "unknown.function")
        to_participant, func_name = full_func_name.split('.', 1)
        
        lines.append(f"    {from_participant}->>+{to_participant}: {func_name}()")
        
        if "nested_calls" in entry:
            lines.extend(_generate_mermaid_lines(entry["nested_calls"], to_participant))
        
        return_value = "exception" if "exception" in entry else "return_value"
        lines.append(f"    {to_participant}-->>-{from_participant}: {return_value}")
        
    return lines

def _generate_sequence_diagram(trace_log: List[Dict[str, Any]], scenario_name: str) -> str:
    """Generates a full Mermaid sequence diagram from a trace log."""
    participants = _get_participants_from_trace(trace_log)
    
    mermaid_string = "```mermaid\n"
    mermaid_string += "sequenceDiagram\n"
    mermaid_string += "    autonumber\n"
    mermaid_string += "    actor Client\n"
    
    for p in participants:
        if p != "Client":
            mermaid_string += f"    participant {p}\n"
            
    mermaid_string += "\n"
    # The initial calls in the trace are from the Client to the first participant.
    first_participant = participants[0] if participants else "Server"
    mermaid_string += "\n".join(_generate_mermaid_lines(trace_log, "Client"))
    mermaid_string += "\n```"
    return mermaid_string

class ScenarioRunner:
    """
    An E2E test runner that starts the application, connects as a real client,
    runs a single scenario, and captures its trace log.
    """
    def __init__(self):
        self.sio = socketio.Client()
        self.task_complete_event = threading.Event()
        self.trace_log = None
        self.haven_trace_log = None
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

        @self.sio.on('haven_trace_log_response')
        def on_haven_trace_log_response(data):
            """Receives the Haven trace log from the server."""
            self.haven_trace_log = data.get("trace")
            self.task_complete_event.set()

    def run_scenario(self, scenario_name, scenario_config):
        print(f"\n--- Running Scenario: {scenario_name} ---")
        self.sio.connect(APP_URL, wait_timeout=10, auth={'is_runner': True})

        # 1. Execute scenario steps.
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

        # 2. Request the trace log from the server.
        self.task_complete_event.clear()
        self.trace_log = None
        self.sio.emit('get_trace_log')
        self.task_complete_event.wait(timeout=5)

        # 3. Request the Haven trace log from the server.
        print("  Client: Requesting Haven trace log...")
        self.task_complete_event.clear()
        self.haven_trace_log = None
        self.sio.emit('get_haven_trace_log')
        self.task_complete_event.wait(timeout=5)

        # 4. Disconnect and save the results.
        self.sio.disconnect()
        self.save_results(scenario_name, scenario_config)
        print(f"--- Scenario Complete. ---")

    def save_results(self, scenario_name, scenario_config):
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # --- Step 1: Save the raw JSON trace map (unchanged) ---
        json_path = os.path.join(OUTPUT_DIR, f"{scenario_name}.json")
        output_data = {
            "scenario_name": scenario_name,
            "description": scenario_config["description"],
            "trace": self.trace_log or "Trace log could not be retrieved."
        }
        with open(json_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Trace map JSON saved to '{json_path}'")

        # --- Step 2: Generate and save the sequence diagram (additive) ---
        if self.trace_log:
            diagram_content = _generate_sequence_diagram(self.trace_log, scenario_name)
            md_path = os.path.join(OUTPUT_DIR, f"{scenario_name}_sequence.md")
            with open(md_path, "w") as f:
                f.write(f"# Sequence Diagram for: {scenario_name}\n\n")
                f.write(f"**Description**: {scenario_config['description']}\n\n")
                f.write(diagram_content)
            print(f"Sequence diagram saved to '{md_path}'")

        # --- Step 3: Generate and save the Haven sequence diagram ---
        if self.haven_trace_log:
            # Save the raw Haven trace JSON
            haven_json_path = os.path.join(OUTPUT_DIR, f"{scenario_name}_haven.json")
            haven_output_data = {
                "scenario_name": f"{scenario_name} (Haven)",
                "description": scenario_config["description"],
                "trace": self.haven_trace_log
            }
            with open(haven_json_path, "w") as f:
                json.dump(haven_output_data, f, indent=2)
            print(f"Haven trace map JSON saved to '{haven_json_path}'")

            # Save the Haven sequence diagram
            haven_diagram_content = _generate_sequence_diagram(self.haven_trace_log, scenario_name)
            haven_md_path = os.path.join(OUTPUT_DIR, f"{scenario_name}_haven_sequence.md")
            with open(haven_md_path, "w") as f:
                f.write(f"# Sequence Diagram for: {scenario_name} (Haven Service)\n\n")
                f.write(f"**Description**: {scenario_config['description']}\n\n")
                f.write(haven_diagram_content)
            print(f"Haven sequence diagram saved to '{haven_md_path}'")


def main():
    """
    Main function to start servers, run scenarios, and stop servers.
    """
    # The main loop now encapsulates the entire lifecycle for each scenario.
    for name, config in SCENARIOS.items():
        haven_process = None
        app_process = None
        try:
            # Start Haven for the current scenario
            print(f"\n--- [{name}] Starting Services ---")
            print("Starting Haven service...")
            haven_process = subprocess.Popen([sys.executable, "haven.py"])
            time.sleep(5) # Wait for Haven to be ready

            # Start the Flask App for the current scenario
            print("Starting Flask App service...")
            app_process = subprocess.Popen([sys.executable, "phoenix.py"])
            time.sleep(5) # Wait for Flask app to be ready

            # Run the single scenario with the fresh services.
            runner = ScenarioRunner()
            runner.run_scenario(name, config)

        finally:
            # Ensure all background processes are terminated after the scenario.
            print(f"--- [{name}] Tearing Down Services ---")
            if app_process:
                print("Terminating Flask App service...")
                app_process.terminate()
                app_process.wait()
            if haven_process:
                print("Terminating Haven service...")
                haven_process.terminate()
                haven_process.wait()
            print("--- Teardown Complete ---")


if __name__ == "__main__":
    main()
