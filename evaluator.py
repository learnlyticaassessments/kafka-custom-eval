import os
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# === CONFIGURATION ===
INPUT_CSV = "input.csv"
REMOTE_PATH = "/home/ubuntu/opt/.kafka_envs/kafka_13ui/kafka-feb25-org-akhil-89/"  # Folder to copy from on each machine
ASSIGNMENT_SUBDIR = "assignments"
SSH_USER = "ubuntu"
PEM_PATH = os.getenv("PEM_PATH", os.path.expanduser("~/.ssh/id_rsa"))
LOCAL_TESTS_DIR = os.path.join(os.getcwd(), "tests")

def read_candidates(csv_file):
    candidates = []
    with open(csv_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append({
                "candidate_id": row["candidate_id"],
                "ip": row["ip"]
            })
    return candidates

def fetch_assignments_only(ip, local_path):
    os.makedirs(local_path, exist_ok=True)
    remote_assignments = f"{SSH_USER}@{ip}:{os.path.join(REMOTE_PATH, ASSIGNMENT_SUBDIR)}"
    print(f"[{ip}] Copying assignments from {remote_assignments} -> {local_path}")
    subprocess.run(["scp", "-i", PEM_PATH, "-r", remote_assignments, local_path], check=True)

def evaluate_assignment(candidate_id, assignment_file, eval_dir):
    assignment_name = Path(assignment_file).stem
    test_file = f"test_{assignment_name}.py"
    test_path = os.path.join(LOCAL_TESTS_DIR, test_file)

    if not os.path.exists(test_path):
        print(f"[{candidate_id}] No test found for {assignment_file}. Skipping.")
        return {
            "assignment": assignment_name,
            "status": "no_test",
            "score": 0,
            "output": ""
        }

    # Copy test file into eval dir
    test_dest_dir = os.path.join(eval_dir, "tests")
    os.makedirs(test_dest_dir, exist_ok=True)
    shutil.copy(test_path, os.path.join(test_dest_dir, test_file))

    cmd = [
        "pytest",
        "-v",
        f"tests/{test_file}",
        "--json-report",
        f"--json-report-file=report_{assignment_name}.json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=eval_dir)

    report_file = os.path.join(eval_dir, f"report_{assignment_name}.json")
    if not os.path.exists(report_file):
        return {
            "assignment": assignment_name,
            "status": "failed",
            "score": 0,
            "output": result.stderr
        }

    with open(report_file) as f:
        report = json.load(f)

    try:
        passed = report["summary"]["passed"]
        total = report["summary"]["total"]
        score = passed * 2.5
        return {
            "assignment": assignment_name,
            "status": "success",
            "passed": passed,
            "total": total,
            "score": score,
            "output": result.stdout
        }
    except KeyError:
        return {
            "assignment": assignment_name,
            "status": "malformed_report",
            "score": 0,
            "output": result.stdout
        }

def evaluate_candidate(candidate_id, assignments_dir):
    print(f"\nEvaluating Candidate: {candidate_id}")
    results = []

    for assignment_file in os.listdir(assignments_dir):
        if assignment_file.endswith(".py"):
            with tempfile.TemporaryDirectory() as eval_dir:
                # Create assignments directory
                eval_assignments_dir = os.path.join(eval_dir, ASSIGNMENT_SUBDIR)
                os.makedirs(eval_assignments_dir, exist_ok=True)

                # Copy the single assignment file
                shutil.copy(
                    os.path.join(assignments_dir, assignment_file),
                    os.path.join(eval_assignments_dir, assignment_file)
                )

                result = evaluate_assignment(candidate_id, assignment_file, eval_dir)
                results.append(result)

    return {
        "candidate_id": candidate_id,
        "results": results,
        "total_score": sum(r["score"] for r in results)
    }

def main():
    candidates = read_candidates(INPUT_CSV)
    all_results = []

    temp_root = tempfile.mkdtemp()

    for candidate in candidates:
        cid = candidate["candidate_id"]
        ip = candidate["ip"]
        local_path = os.path.join(temp_root, cid)

        try:
            fetch_assignments_only(ip, local_path)
            assignments_dir = os.path.join(local_path, ASSIGNMENT_SUBDIR)
            result = evaluate_candidate(cid, assignments_dir)
        except Exception as e:
            result = {
                "candidate_id": cid,
                "results": [],
                "total_score": 0,
                "error": str(e),
            }

        all_results.append(result)

    os.makedirs("results", exist_ok=True)
    with open("results/evaluation_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\nFinal Summary:")
    for res in all_results:
        print(f"{res['candidate_id']}: {res.get('total_score', 0)}/10")

if __name__ == "__main__":
    main()
