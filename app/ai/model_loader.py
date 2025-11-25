# app/ai/model_loader.py
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"


class ModelFileMissing(RuntimeError):
    pass


def _load_pickle(path: Path) -> Any:
    if not path.exists():
        raise ModelFileMissing(f"Model file missing: {path}")
    with path.open("rb") as f:
        return pickle.load(f)


@lru_cache(maxsize=1)
def get_eligibility_model() -> Any:
    return _load_pickle(MODELS_DIR / "eligibility.pkl")


@lru_cache(maxsize=1)
def get_intent_model_and_vec() -> tuple[Any, Any]:
    nb = _load_pickle(MODELS_DIR / "intent_nb.pkl")
    vec = _load_pickle(MODELS_DIR / "intent_vectorizer.pkl")
    return nb, vec
