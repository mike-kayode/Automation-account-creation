import logging
from pathlib import Path


def configure_logging(directory: str | Path) -> logging.Logger:
	target = Path(directory)
	target.mkdir(parents=True, exist_ok=True)
	logger = logging.getLogger("nairatrader")
	logger.setLevel(logging.INFO)
	if not logger.handlers:
		handler = logging.FileHandler(target / "worker.log", encoding="utf-8")
		handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
		logger.addHandler(handler)
	return logger
