import datetime
from services.subsidy_claim_service import get_subsidy_claims


def test_subsidy_claim_grouping_and_totals():
    cases = [
        # Case 1: Q4 2025 -> due Jan 2026
        {
            "case_no": "114000001",
            "subsidy_hours": 40.0,
            "subsidy_salary": 12000.0,
            "actual_end_date": "2025-10-15",
            "end_date": "2025-10-15"
        },
        # Case 2: Q1 2026 -> due Apr 2026
        {
            "case_no": "115000001",
            "subsidy_hours": 120.0,
            "subsidy_salary": 42000.0,
            "actual_end_date": datetime.date(2026, 2, 10),
            "end_date": None
        },
        # Case 3: Q2 2026 -> due Jul 2026
        {
            "case_no": "115000002",
            "subsidy_hours": 40.0,
            "subsidy_salary": 12000.0,
            "actual_end_date": None,
            "end_date": "2026-05-15"
        },
        # Case 4: Q3 2026 -> due Oct 2026
        {
            "case_no": "115000003",
            "subsidy_hours": 40.0,
            "subsidy_salary": 12000.0,
            "actual_end_date": "2026-08-20",
            "end_date": "2026-08-25"
        },
        # Case 5: Q4 2026 -> due Jan 2027 (Excluded from 2026)
        {
            "case_no": "115000004",
            "subsidy_hours": 40.0,
            "subsidy_salary": 12000.0,
            "actual_end_date": "2026-11-10",
            "end_date": "2026-11-10"
        },
        # Case 6: subsidy_hours is 0 (Excluded)
        {
            "case_no": "115000005",
            "subsidy_hours": 0.0,
            "subsidy_salary": 0.0,
            "actual_end_date": "2026-02-10",
            "end_date": "2026-02-10"
        }
    ]
    
    result = get_subsidy_claims(cases, 2026)
    
    assert len(result["quarterly_candidates"]["January"]) == 1
    assert result["quarterly_candidates"]["January"][0]["case_no"] == "114000001"
    
    assert len(result["quarterly_candidates"]["April"]) == 1
    assert result["quarterly_candidates"]["April"][0]["case_no"] == "115000001"
    
    assert len(result["quarterly_candidates"]["July"]) == 1
    assert result["quarterly_candidates"]["July"][0]["case_no"] == "115000002"
    
    assert len(result["quarterly_candidates"]["October"]) == 1
    assert result["quarterly_candidates"]["October"][0]["case_no"] == "115000003"
    
    overview = result["annual_overview"]
    assert overview["expected"] == 78000.0
    assert overview["submitted"] == 0.0
    assert overview["approved"] == 0.0
    assert overview["paid"] == 0.0
