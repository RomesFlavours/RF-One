"""Deterministic phone extraction (fix A2, 2026-11-15).

The cases reproduce, with synthetic digits, the shapes found in the migrated
production CVs: a number written as "(407) 555-...", a ZIP code right before
the number, and employment year ranges.  No real CV is read or changed.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'RF-One Data Store'))
from rfone_data_store.selection.parsing import deterministic_parser as dp


class PhoneParserTests(unittest.TestCase):
    def test_keeps_opening_parenthesis(self):
        self.assertEqual(dp.find_phone('Jordan Example\njordan@example.test  (407) 555-0101\n'), '(407) 555-0101')

    def test_parenthesis_without_space(self):
        self.assertEqual(dp.find_phone('Phone: (321)555-0177'), '(321)555-0177')

    def test_zip_code_is_not_absorbed(self):
        self.assertEqual(dp.find_phone('123 Main St, Orlando, FL 32801 (407) 555-0199'), '(407) 555-0199')
        self.assertEqual(dp.find_phone('Kissimmee, FL 34741 407-555-0142'), '407-555-0142')
        self.assertEqual(dp.find_phone('Orlando FL 32819 4075550123'), '4075550123')

    def test_date_ranges_are_not_phones(self):
        for text in ('Server | 2019 - 2021', 'Cook 2015-2019 2020', 'Mar 2021 - Present',
                     '01/2018 - 12/2020', '2012 – 2016 Valencia College'):
            self.assertIsNone(dp.find_phone(text), text)

    def test_date_range_before_the_phone(self):
        self.assertEqual(dp.find_phone('Host 2019 - 2021\nCell 689.555.0110'), '689.555.0110')

    def test_correct_numbers_unchanged(self):
        for number in ('407-555-0101', '407.555.0101', '407 555 0101', '4075550101', '+1 407 555 0101',
                       '+1 (407) 555-0101', '1-407-555-0101', '+39 333 123 4567', '+44 20 7946 0958'):
            self.assertEqual(dp.find_phone(f'Contact: {number} email x@example.test'), number)

    def test_never_joins_lines(self):
        # Shapes seen in the migrated CVs: ZIP or street number on the line above, ZIP on the line below.
        self.assertEqual(dp.find_phone('Orlando, FL 32801\n(407) 555-0144'), '(407) 555-0144')
        self.assertEqual(dp.find_phone('+1 407 555 0155\n1133 Example Ave'), '+1 407 555 0155')
        self.assertEqual(dp.find_phone('407-555-0166\n32819'), '407-555-0166')
        self.assertIsNone(dp.find_phone('407\n555\n0177'))

    def test_short_or_long_digit_runs_are_ignored(self):
        self.assertIsNone(dp.find_phone('Badge 555-0101'))
        self.assertIsNone(dp.find_phone('Order 40755501012345'))

    def test_parser_contact_field(self):
        text = ('Casey Sample\nOrlando, FL 32801 (407) 555-0133\ncasey@example.test\n\n'
                'EXPERIENCE\nServer, Trattoria Prova, Orlando, FL | 2019 - 2021\n')
        parsed = dp.DeterministicResumeParser().parse(SimpleNamespace(raw_text=text, original_filename='casey.txt'))
        self.assertEqual(parsed.phone, '(407) 555-0133')
        self.assertEqual(parsed.full_name, 'Casey Sample')


if __name__ == '__main__':
    unittest.main()
