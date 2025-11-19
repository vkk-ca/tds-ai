import unittest
from datetime import datetime
import json

# Load section mapping
with open('data/sections.json', 'r') as f:
    SECTION_MAP = json.load(f)

def calc_interest(row):
    def to_date(s):
        try:
            return datetime.strptime(str(s)[:10], '%Y-%m-%d')
        except:
            return None
    dt_trans = to_date(row['date_of_transaction'])
    dt_deduct = to_date(row['date_of_tax_deduction'])
    dt_pay = to_date(row['date_of_tax_payment'])
    if not (dt_trans and dt_deduct and dt_pay):
        return 0.0
    principal = float(row['principal_amount'])
    section = str(row['tax_code_section']).strip()
    tds = principal * SECTION_MAP.get(section, 0)
    deadline_month = dt_trans.month + 1 if dt_trans.month < 12 else 1
    deadline_year = dt_trans.year if dt_trans.month < 12 else dt_trans.year + 1
    deadline_day = 7
    deadline = datetime(deadline_year, deadline_month, deadline_day)
    if dt_pay <= deadline:
        return 0.0
    is_year_end = dt_deduct.month == 3 and dt_deduct.day == 31
    if is_year_end:
        dt_deduct = datetime(dt_deduct.year + 1, 4, 1)
        if dt_pay <= datetime(dt_deduct.year, 4, 30):
            months_1 = 2
            interest = tds * 0.01 * months_1
            return round(interest, 2)
        else:
            months_1 = 2
            months_15 = (dt_pay.year - dt_deduct.year) * 12 + (dt_pay.month - 4) + 1
            interest = tds * 0.01 * months_1 + tds * 0.015 * months_15
            return round(interest, 2)
    months_1 = (dt_deduct.year - dt_trans.year) * 12 + (dt_deduct.month - dt_trans.month)
    if months_1 < 0:
        months_1 = 0
    months_15 = (dt_pay.year - dt_deduct.year) * 12 + (dt_pay.month - dt_deduct.month) + 1
    if months_15 < 0:
        months_15 = 0
    interest = tds * 0.01 * months_1 + tds * 0.015 * months_15
    return round(interest, 2)

class TestTDSInterest(unittest.TestCase):
    def test_on_time_payment(self):
        row = {
            'principal_amount': 150000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '2025-02-10',
            'date_of_tax_deduction': '2025-02-25',
            'date_of_tax_payment': '2025-03-07'
        }
        self.assertEqual(calc_interest(row), 0.0)

    def test_one_day_late(self):
        row = {
            'principal_amount': 150000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '2025-02-10',
            'date_of_tax_deduction': '2025-02-25',
            'date_of_tax_payment': '2025-03-08'
        }
        self.assertEqual(calc_interest(row), 450.0)

    def test_deduction_next_month(self):
        row = {
            'principal_amount': 150000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '2025-02-10',
            'date_of_tax_deduction': '2025-03-01',
            'date_of_tax_payment': '2025-04-01'
        }
        self.assertEqual(calc_interest(row), 600.0)

    def test_year_end_paid_before_apr30(self):
        row = {
            'principal_amount': 150000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '2025-02-10',
            'date_of_tax_deduction': '2025-03-31',
            'date_of_tax_payment': '2025-04-30'
        }
        self.assertEqual(calc_interest(row), 300.0)

    def test_year_end_paid_after_apr30(self):
        row = {
            'principal_amount': 150000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '2025-02-10',
            'date_of_tax_deduction': '2025-03-31',
            'date_of_tax_payment': '2025-06-01'
        }
        self.assertEqual(calc_interest(row), 975.0)

    # Additional test cases
    def test_no_interest_for_early_payment(self):
        row = {
            'principal_amount': 100000.00,
            'tax_code_section': '94C',
            'date_of_transaction': '2025-01-15',
            'date_of_tax_deduction': '2025-01-20',
            'date_of_tax_payment': '2025-02-07'
        }
        self.assertEqual(calc_interest(row), 0.0)

    def test_interest_multiple_months(self):
        row = {
            'principal_amount': 200000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '2025-01-10',
            'date_of_tax_deduction': '2025-03-10',
            'date_of_tax_payment': '2025-05-10'
        }
        # Jan, Feb at 1% (2 months), Mar, Apr, May at 1.5% (3 months)
        tds = 200000 * 0.10
        expected = tds * 0.01 * 2 + tds * 0.015 * 3
        self.assertEqual(calc_interest(row), round(expected, 2))

    def test_invalid_dates(self):
        row = {
            'principal_amount': 100000.00,
            'tax_code_section': '94A',
            'date_of_transaction': '',
            'date_of_tax_deduction': '',
            'date_of_tax_payment': ''
        }
        self.assertEqual(calc_interest(row), 0.0)

if __name__ == '__main__':
    unittest.main()
