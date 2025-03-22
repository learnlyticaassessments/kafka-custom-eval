import os
import json
import pandas as pd

def main():
    # Path to the aggregated evaluation results
    json_path = os.path.join("results", "evaluation_results.json")
    
    # Load the evaluation results
    with open(json_path, "r") as f:
        results = json.load(f)
    
    data = []
    for rec in results:
        candidate_id = rec.get("candidate_id", "Unknown")
        total_tests = rec.get("total_tests", 0)
        passed_tests = rec.get("total_passed", 0)
        percentage = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        # Simulate individual test results
        test_results = {}
        for i, test in enumerate(rec.get("results", []), start=1):
            test_results[f"Test {i}"] = "Pass" if test.get("passed", 0) > 0 else "Fail"

        record = {
            "Candidate ID": candidate_id,
            "Total Test Cases": total_tests,
            "Total Passed": passed_tests,
            "Pass Percentage (%)": round(percentage, 2)
        }
        record.update(test_results)
        data.append(record)
    
    # Create DataFrame and write Excel file
    df = pd.DataFrame(data)
    excel_filename = "evaluation_report.xlsx"
    df.to_excel(excel_filename, index=False)
    print("Excel report created:", excel_filename)

if __name__ == "__main__":
    main()
