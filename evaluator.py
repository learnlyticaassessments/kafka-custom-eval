import os
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import logging
import traceback

# === CONFIGURATION ===
INPUT_CSV = "input.csv"
REMOTE_PATH = "/home/ubuntu/opt/.kafka_envs/kafka_13ui/kafka-feb25-org-akhil-89/"
ASSIGNMENT_SUBDIR = "assignments"
SSH_USER = "ubuntu"
PEM_PATH = os.getenv("PEM_PATH", os.path.expanduser("~/.ssh/id_rsa"))
LOCAL_TESTS_DIR = os.path.join(os.getcwd(), "tests")

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.DEBUG,  # Show all debug info
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def read_candidates(csv_file):
    candidates = []
    try:
        with open(csv_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                candidates.append({
                    "candidate_id": row["candidate_id"],
                    "ip": row["ip"]
                })
        logging.info(f"Loaded {len(candidates)} candidates from {csv_file}")
    except Exception as e:
        logging.error(f"Failed to read input CSV: {e}")
        raise
    return candidates

def fetch_assignments_only(ip, local_path):
    os.makedirs(local_path, exist_ok=True)
    remote_assignments = f"{SSH_USER}@{ip}:{os.path.join(REMOTE_PATH, ASSIGNMENT_SUBDIR)}"
    logging.info(f"[{ip}] Copying assignments from {remote_assignments} -> {local_path}")
    try:
        subprocess.run(["scp", "-i", PEM_PATH, "-r", remote_assignments, local_path], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"[{ip}] SCP failed: {e}")
        raise

def log_eval_dir_contents(eval_dir, candidate_id):
    logging.debug(f"[{candidate_id}] Contents of eval_dir ({eval_dir}):")
    for root, dirs, files in os.walk(eval_dir):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), eval_dir)
            logging.debug(f"[{candidate_id}] - {rel_path}")


def evaluate_assignment(candidate_id, assignment_file, eval_dir):
    assignment_name = Path(assignment_file).stem
    test_file = f"test_{assignment_name}.py"
    test_path = os.path.join(LOCAL_TESTS_DIR, test_file)

    if not os.path.exists(test_path):
        logging.warning(f"[{candidate_id}] No test found for {assignment_file}. Skipping.")
        return {
            "assignment": assignment_name,
            "status": "no_test",
            "total": 0,
            "passed": 0,
            "output": ""
        }

    test_dest_dir = os.path.join(eval_dir, "tests")
    os.makedirs(test_dest_dir, exist_ok=True)
    shutil.copy(test_path, os.path.join(test_dest_dir, test_file))

    logging.info(f"[{candidate_id}] Running test for {assignment_file}")
    cmd = [
        "pytest",
        "-v",
        f"tests/{test_file}",
        "--json-report",
        f"--json-report-file=report_{assignment_name}.json"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=eval_dir)
    except subprocess.SubprocessError as e:
        logging.error(f"[{candidate_id}] Pytest subprocess failed: {e}")
        return {
            "assignment": assignment_name,
            "status": "error",
            "total": 0,
            "passed": 0,
            "output": str(e)
        }

    report_file = os.path.join(eval_dir, f"report_{assignment_name}.json")
    if not os.path.exists(report_file):
        logging.error(f"[{candidate_id}] Report file not found for {assignment_name}")
        return {
            "assignment": assignment_name,
            "status": "failed",
            "total": 0,
            "passed": 0,
            "output": result.stderr
        }

    with open(report_file) as f:
        report = json.load(f)

    try:
        summary = report.get("summary", {})
        passed = summary.get("passed", 0)
        total = summary.get("total", 0)
        failed = summary.get("failed", 0)

        logging.info(f"[{candidate_id}] {assignment_name}: Passed {passed}/{total}")
        return {
            "assignment": assignment_name,
            "status": "success",
            "passed": passed,
            "total": total,
            "output": result.stdout
        }
    except Exception as e:
        logging.error(f"[{candidate_id}] Unexpected error parsing test report: {e}")
        logging.debug(f"[{candidate_id}] Full test report:\n{json.dumps(report, indent=2)}")
        return {
            "assignment": assignment_name,
            "status": "malformed_report",
            "total": 0,
            "passed": 0,
            "output": result.stdout
        }

def evaluate_candidate(candidate_id, assignments_dir):
    logging.info(f"=== Evaluating {candidate_id} ===")
    results = []
    total_tests = 0
    total_passed = 0

    for assignment_file in os.listdir(assignments_dir):
        if assignment_file.endswith(".py"):
            with tempfile.TemporaryDirectory() as eval_dir:
                eval_assignments_dir = os.path.join(eval_dir, ASSIGNMENT_SUBDIR)
                os.makedirs(eval_assignments_dir, exist_ok=True)

                shutil.copy(
                    os.path.join(assignments_dir, assignment_file),
                    os.path.join(eval_assignments_dir, assignment_file)
                )

                try:
                    result = evaluate_assignment(candidate_id, assignment_file, eval_dir)
                except Exception as e:
                    logging.error(f"[{candidate_id}] Exception during test run for {assignment_file}: {e}")
                    logging.debug(traceback.format_exc())
                    result = {
                        "assignment": Path(assignment_file).stem,
                        "status": "error",
                        "passed": 0,
                        "total": 0,
                        "output": str(e)
                    }

                total_tests += result.get("total", 0)
                total_passed += result.get("passed", 0)
                results.append(result)

    logging.info(f"[{candidate_id}] Total Passed: {total_passed}/{total_tests}")
    return {
        "candidate_id": candidate_id,
        "results": results,
        "total_tests": total_tests,
        "total_passed": total_passed
    }


def main():
    logging.info("=== Starting Evaluation ===")
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
            if not os.path.exists(assignments_dir):
                raise FileNotFoundError(f"'assignments' folder not found in {local_path}")
            result = evaluate_candidate(cid, assignments_dir)
        except Exception as e:
            logging.error(f"[{cid}] Failed to evaluate: {e}")
            logging.debug(traceback.format_exc())
            result = {
                "candidate_id": cid,
                "results": [],
                "total_score": 0,
                "error": str(e),
            }

        all_results.append(result)

    os.makedirs("results", exist_ok=True)
    result_path = "results/evaluation_results.json"
    with open(result_path, "w") as f:
        json.dump(all_results, f, indent=2)

    logging.info(f"Evaluation complete. Results saved to {result_path}")
    logging.info("=== Final Summary ===")
    for res in all_results:
        score = res.get("total_score", 0)
        logging.info(f"{res['candidate_id']}: {score}/10")

if __name__ == "__main__":
    main()
