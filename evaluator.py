import os
import csv
import json
import shutil
import argparse
import subprocess
import tempfile
from pathlib import Path
from git import Repo

SSH_USER = "ubuntu"
PEM_PATH = os.getenv("PEM_PATH", os.path.expanduser("~/.ssh/id_rsa"))
ASSIGNMENT_DIR = "assignments"
ASSIGNMENT = "kafka_app"

def fetch_code_from_machine(ip, remote_path, local_dest):
    os.makedirs(local_dest, exist_ok=True)
    remote = f"{SSH_USER}@{ip}:{remote_path}"
    print(f"Pulling code from {remote}...")
    subprocess.run([
        "scp", "-i", PEM_PATH, "-r", remote, local_dest
    ], check=True)

def evaluate_candidate(candidate_id, local_code_path, srepo_path):
    print(f"\nEvaluating Candidate: {candidate_id}")
    with tempfile.TemporaryDirectory() as eval_dir:
        # Copy srepo into eval dir
        shutil.copytree(srepo_path, eval_dir, dirs_exist_ok=True)

        # Replace assignments folder
        target_path = os.path.join(eval_dir, ASSIGNMENT_DIR)
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        shutil.copytree(local_code_path, target_path)

        # Run tests
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
                return {"candidate_id": candidate_id, "status": "error", "error": "Malformed test report", "score": 0}
        else:
            return {"candidate_id": candidate_id, "status": "failed", "error": "No test report", "score": 0}

def read_csv(file_path):
    candidates = []
    with open(file_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            candidates.append({
                "candidate_id": row["candidate_id"],
                "ip": row["ip"]
            })
    return candidates

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--srepo_url", required=True, help="URL of the central evaluator repo")
    parser.add_argument("--input_csv", required=True, help="CSV with candidate_id,ip")
    parser.add_argument("--remote_path", required=True, help="Remote path to pull code from each machine")
    args = parser.parse_args()

    candidates = read_csv(args.input_csv)
    all_results = []

    # Clone srepo
    with tempfile.TemporaryDirectory() as srepo_temp:
        print(f"Cloning srepo from {args.srepo_url}...")
        Repo.clone_from(args.srepo_url, srepo_temp)

        code_temp_dir = tempfile.mkdtemp()

        for candidate in candidates:
            cid = candidate["candidate_id"]
            ip = candidate["ip"]
            candidate_path = os.path.join(code_temp_dir, cid)

            try:
                fetch_code_from_machine(ip, args.remote_path, candidate_path)
                result = evaluate_candidate(cid, candidate_path, srepo_temp)
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
    for r in all_results:
        print(f"{r['candidate_id']}: {r['score']}/10 ({r['status']})")

if __name__ == "__main__":
    main()
