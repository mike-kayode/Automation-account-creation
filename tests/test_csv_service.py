import csv

from services.csv_service import save_account_and_verify


def test_save_account_appends_and_verifies(tmp_path):
	first = save_account_and_verify("477175749", "$Manager12345", "NairaTrader 1.5M", tmp_path)
	second = save_account_and_verify("477175882", "$Manager58321", "NairaTrader 1.5M", tmp_path)

	assert first == second == tmp_path / "accounts.csv"
	with second.open(newline="", encoding="utf-8") as file:
		assert list(csv.reader(file)) == [
			["MT5 Number", "Password", "Nickname"],
			["477175749", "$Manager12345", "NairaTrader 1.5M"],
			["477175882", "$Manager58321", "NairaTrader 1.5M"],
		]


def test_duplicate_row_is_not_written_twice(tmp_path):
	first = save_account_and_verify("477175749", "$Manager12345", "NairaTrader 1.5M", tmp_path)
	again = save_account_and_verify("477175749", "$Manager12345", "NairaTrader 1.5M", tmp_path)

	assert first == again
	with again.open(newline="", encoding="utf-8") as file:
		rows = list(csv.reader(file))
	assert len(rows) == 2


def test_legacy_two_column_report_is_upgraded(tmp_path):
	path = tmp_path / "accounts.csv"
	path.write_text("MT5 Number,Password\n477161681,$Manager00001\n", encoding="utf-8")

	save_account_and_verify("477215991", "$Manager11111", "NairaTrader 1.5M", tmp_path)

	with path.open(newline="", encoding="utf-8") as file:
		assert list(csv.reader(file)) == [
			["MT5 Number", "Password", "Nickname"],
			["477161681", "$Manager00001", ""],
			["477215991", "$Manager11111", "NairaTrader 1.5M"],
		]