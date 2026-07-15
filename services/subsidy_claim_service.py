from datetime import datetime, date


def get_completion_date(case: dict) -> date | None:
    d = case.get("actual_end_date") or case.get("end_date")
    if not d:
        return None
    if isinstance(d, str):
        try:
            return datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    elif isinstance(d, (datetime, date)):
        if isinstance(d, datetime):
            return d.date()
        return d
    return None


def get_claim_due_info(completion_date: date) -> tuple[int, str]:
    year = completion_date.year
    month = completion_date.month
    if 1 <= month <= 3:
        return year, "April"
    elif 4 <= month <= 6:
        return year, "July"
    elif 7 <= month <= 9:
        return year, "October"
    else:
        return year + 1, "January"


def get_subsidy_claims(cases: list[dict], application_year: int) -> dict:
    """
    Groups completed cases by their claim due month (January, April, July, October)
    for the specified application_year, and calculates the annual totals.
    """
    quarterly_candidates = {
        "January": [],
        "April": [],
        "July": [],
        "October": []
    }
    
    expected_total = 0.0
    
    for case in cases:
        subsidy_hours = float(case.get("subsidy_hours") or 0.0)
        if subsidy_hours <= 0:
            continue
            
        comp_date = get_completion_date(case)
        if not comp_date:
            continue
            
        due_year, due_month = get_claim_due_info(comp_date)
        if due_year == application_year:
            quarterly_candidates[due_month].append(case)
            expected_total += float(case.get("subsidy_salary") or 0.0)
            
    annual_overview = {
        "expected": expected_total,
        "submitted": 0.0,
        "approved": 0.0,
        "paid": 0.0
    }
    
    return {
        "quarterly_candidates": quarterly_candidates,
        "annual_overview": annual_overview
    }
