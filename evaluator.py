import os
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from git import Repo

# === CONFIGURATION ===
SREPO_URL = "https://github.com/learnlyticaassessments/kafka-assignment"  # Replace with your actual URL
INPUT_CSV = "input.csv"
REMOTE_PATH = "/home/ubuntu/opt/.kafka_envs/kafka_13ui/kafka-feb25-org-akhil-89/"  # Folder to copy from on each machine
SSH_USER = "ubuntu"
PEM_PATH = os.getenv("PEM_PATH", os.path.expanduser("~/.ssh/id_rsa"))  # Private key should be loaded by GH Actions
ASSIGNMENT_DIR = "assignments"
ASSIGNMENT = "kafka_app"

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

def fetch_code(ip, local_path):
    os.makedirs(local_path, exist_ok=True)
    remote = f"{SSH_USER}@{ip}:{REMOTE_PATH}"
    print(f"[{ip}] Fetching code from {remote} -> {local_path}")
    subprocess.run(["scp", "-i", PEM_PATH, "-r", remote, local_path], check=True)

def evaluate(candidate_id, local_code_path, srepo_path):
    print(f"\nEvaluating Candidate: {candidate_id}")
    with tempfile.TemporaryDirectory() as eval_dir:
        shutil.copytree(srepo_path, eval_dir, dirs_exist_ok=True)

        # Replace assignments directory with candidate's code
        dest_path = os.path.join(eval_dir, ASSIGNMENT_DIR)
        if os.path.exists(dest_path):
            shutil.rmtree(dest_path)
        shutil.copytree(local_code_path, dest_path)

        cmd = [
            "pytest",
            "-v",
            f"tests/test_{ASSIGNMENT}.py",
            "--json-report",
            "--json-report-file=report.json"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=eval_dir)
        report_path = os.path.join(eval_dir, "report.json")

        if os.path.exists(report_path):
            with open(report_path) as f:
                report = json.load(f)
            try:
                passed = report["summary"]["passed"]
                total = report["summary"]["total"]
                score = passed * 2.5
                return {
                    "candidate_id": candidate_id,
                    "status": "success",
                    "passed": passed,
                    "total": total,
                    "score": score,
                    "output": result.stdout
                }
            except KeyError:
                return {"candidate_id": candidate_id, "status": "error", "error": "Malformed report", "score": 0}
        else:
            return {"candidate_id": candidate_id, "status": "failed", "error": "No test report", "score": 0}

def main():
    candidates = read_candidates(INPUT_CSV)
    all_results = []

    with tempfile.TemporaryDirectory() as srepo_dir:
        print(f"Cloning srepo from {SREPO_URL}...")
        Repo.clone_from(SREPO_URL, srepo_dir)

        temp_code_dir = tempfile.mkdtemp()

        for candidate in candidates:
            cid = candidate["candidate_id"]
            ip = candidate["ip"]
            local_path = os.path.join(temp_code_dir, cid)

            try:
                fetch_code(ip, local_path)
                result = evaluate(cid, local_path, srepo_dir)
            except Exception as e:
                result = {
                    "candidate_id": cid,
                    "status": "error",
                    "error": str(e),
                    "score": 0
                }

            all_results.append(result)

    # Save results
    os.makedirs("results", exist_ok=True)
    with open("results/evaluation_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print("\nEvaluation Summary:")
    for res in all_results:
        print(f"{res['candidate_id']}: {res['score']}/10 ({res['status']})")

if __name__ == "__main__":
    main()
