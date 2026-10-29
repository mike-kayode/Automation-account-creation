import csv
from pathlib import Path


HEADERS = ["MT5 Number", "Password", "Nickname"]
LEGACY_HEADER = ["MT5 Number", "Password"]


def _upgrade_legacy(path: Path) -> None:
	"""Rewrite an old 2-column report to include the Nickname column.

	Existing rows keep their data; their nickname is unknown here so it is
	left blank (the one-off DB migration backfills real nicknames).
	"""
	with path.open("r", newline="", encoding="utf-8") as file:
		rows = list(csv.reader(file))
	if not rows or rows[0] != LEGACY_HEADER:
		return
	upgraded = [HEADERS] + [[row[0], row[1], ""] for row in rows[1:] if len(row) >= 2]
	with path.open("w", newline="", encoding="utf-8") as file:
		csv.writer(file).writerows(upgraded)


def save_account_and_verify(mt5_number: str, password: str, nickname: str, directory: str | Path) -> Path:
	"""Append one account (MT5 + password + nickname) and verify the exact row was durably written."""
	target = Path(directory)
	target.mkdir(parents=True, exist_ok=True)
	path = target / "accounts.csv"
	if path.exists():
		_upgrade_legacy(path)
		with path.open("r", newline="", encoding="utf-8") as file:
			rows = list(csv.reader(file))
		if any(row == [mt5_number, password, nickname] for row in rows[1:]):
			return path

	with path.open("a+", newline="", encoding="utf-8") as file:
		file.seek(0, 2)
		if file.tell() == 0:
			csv.writer(file).writerow(HEADERS)
		csv.writer(file).writerow([mt5_number, password, nickname])
		file.flush()

	with path.open("r", newline="", encoding="utf-8") as file:
		rows = list(csv.reader(file))
	if not any(row == [mt5_number, password, nickname] for row in rows[1:]):
		raise OSError(f"REPORT_VERIFICATION_FAILED: {mt5_number}")
	return path
