import os
import json
import subprocess
import re
from datetime import datetime

# --- Configuration ---
# Make paths relative to this script's location.
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# Directories where the SDLC artifacts are stored.
REQUIREMENTS_DIR = os.path.join(PROJECT_ROOT, "sdlc/requirements")
TESTS_DIR = os.path.join(PROJECT_ROOT, "sdlc/tests")
RTM_DIR = os.path.join(PROJECT_ROOT, "sdlc/rtm")

# The current version of the code being tested.
CODE_VERSION = "v0.1.0"

def _summarize_failure_reason(longrepr):
    """
    Parses a raw pytest 'longrepr' string to extract a clean, readable JSON object.
    """
    if not isinstance(longrepr, str):
        return {"error": "Invalid failure reason format (not a string)."}

    summary_dict = {
        "location": "N/A",
        "failing_line": "N/A",
        "error_details": []
    }
    lines = longrepr.strip().split('\n')
    
    # Find the file path and error type from the last line
    summary_dict["location"] = lines[-1]

    # Find the exact line of code that failed
    for line in lines:
        if line.strip().startswith('>'):
            summary_dict["failing_line"] = line.strip()[2:]
            break
            
    # Find the specific error details
    error_details = [line.strip()[2:] for line in lines if line.strip().startswith('E ')]
    if error_details:
        summary_dict["error_details"] = error_details

    return summary_dict

def load_all_requirements():
    """
    Scans the requirements directory for the unified RS-Project.json,
    parses it, and returns a dictionary of all requirements keyed by their ID.
    """
    all_reqs = {}
    req_file_path = os.path.join(REQUIREMENTS_DIR, "RS-Project.json")
    print(f"Loading all requirements from '{req_file_path}'...")
    
    if not os.path.exists(req_file_path):
        print(f"Error: Requirements file not found at '{req_file_path}'")
        return {}
    
    with open(req_file_path, 'r') as f:
        data = json.load(f)

    # Load functional requirements from each module
    for module_name, module_data in data.get("modules", {}).items():
        for func_name, req_list in module_data.get("functions", {}).items():
            for req in req_list:
                req['description'] = req.get('requirement', '')
                all_reqs[req['id']] = req

    # Load qualitative requirements
    for category_name, cat_data in data.get("qualitative_requirements", {}).get("categories", {}).items():
        for req in cat_data:
            req['description'] = req.get('requirement', '')
            all_reqs[req['id']] = req

    print(f"Found {len(all_reqs)} total requirements.")
    return all_reqs

def run_tests_and_get_results():
    """
    Runs pytest, captures detailed results including failure reasons from the
    JSON report, and returns a dictionary of the results.
    """
    report_file = os.path.join(PROJECT_ROOT, ".pytest_report.json")
    print(f"\nRunning all test protocols in '{TESTS_DIR}' via pytest...")
    
    try:
        process = subprocess.run(
            ["pytest", TESTS_DIR, "--json-report", f"--json-report-file={report_file}"],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True,
            check=False
        )
        if process.returncode != 0:
            print("Pytest execution finished with failing tests.")
        else:
            print("Pytest execution completed successfully.")

    except FileNotFoundError:
        print("Error: 'pytest' command not found. Make sure pytest is installed and in your PATH.")
        return {}

    if not os.path.exists(report_file):
        print(f"Error: Pytest report file '{report_file}' not found.")
        return {}

    with open(report_file, 'r') as f:
        report = json.load(f)
    
    test_results = {}
    for test in report.get("tests", []):
        nodeid = test["nodeid"]
        status = "Passed" if test["outcome"] == "passed" else "Failed"
        failure_reason = "N/A"
        
        if status == "Failed":
            raw_longrepr = None
            if test.get('call') and test['call'].get('longrepr'):
                raw_longrepr = test['call']['longrepr']
            elif test.get('setup') and test['setup'].get('longrepr'):
                raw_longrepr = test['setup']['longrepr']
            
            if raw_longrepr:
                failure_reason = _summarize_failure_reason(raw_longrepr)
            else:
                failure_reason = {"error": "Failure reason could not be located in the test report's 'call' or 'setup' phases."}

        test_results[nodeid] = {"status": status, "failure_reason": failure_reason}
        
    # Keep the report for manual inspection if needed, but it can be deleted.
    # os.remove(report_file)
    return test_results

def generate_rtm_json(all_requirements, test_results):
    """
    Generates the final RTM JSON structure by mapping test results
    to the master list of requirements.
    """
    rtm_entries = []
    tested_req_ids = set()

    # Map test results back to requirement IDs
    for nodeid, result_data in test_results.items():
        prefix_match = re.search(r"test_([A-Z]{3}_[A-Z]{3})", nodeid, re.IGNORECASE)
        if prefix_match:
            prefix = prefix_match.group(1)
            base_id = prefix.replace('_', '-')
            
            func_name_body = nodeid.split(prefix)[-1]
            numbers = re.findall(r"(\d{3})", func_name_body)
            
            req_ids_in_test = [f"{base_id}-{num}" for num in numbers]
            
            for req_id in req_ids_in_test:
                req_id = req_id.upper()
                if req_id in all_requirements and req_id not in tested_req_ids:
                    rtm_entries.append({
                        "requirement_id": req_id,
                        "description": all_requirements[req_id]['description'],
                        "test_protocol_id": nodeid.split('::')[0],
                        "status": result_data["status"],
                        "code_version": CODE_VERSION,
                        "test_date_and_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "failure_reason": result_data["failure_reason"]
                    })
                    tested_req_ids.add(req_id)

    # Add all other requirements that were not tested as 'Pending'
    for req_id, req_data in all_requirements.items():
        if req_id not in tested_req_ids:
            protocol_id = "Manual Audit" if req_id.startswith("QLT") else "TBD"
            rtm_entries.append({
                "requirement_id": req_id,
                "description": req_data['description'],
                "test_protocol_id": protocol_id,
                "status": "Pending",
                "code_version": "N/A",
                "test_date_and_time": "N/A",
                "failure_reason": "N/A"
            })
            
    rtm_entries.sort(key=lambda x: x['requirement_id'])

    return {
        "project": "Phoenix Agent",
        "document_version": "2.3",
        "description": "This document traces all project requirements to their test protocols and records the validation status. Auto-generated by generate_rtm.py.",
        "traceability_matrix": rtm_entries
    }

def main():
    """Main execution function."""
    all_requirements = load_all_requirements()
    test_results = run_tests_and_get_results()
    
    rtm_data = generate_rtm_json(all_requirements, test_results)
    
    os.makedirs(RTM_DIR, exist_ok=True)
    output_path = os.path.join(RTM_DIR, "RTM-Project.json")
    
    with open(output_path, 'w') as f:
        json.dump(rtm_data, f, indent=2)
        
    print(f"\nSuccessfully generated Project RTM at '{output_path}'")

if __name__ == "__main__":
    main()
