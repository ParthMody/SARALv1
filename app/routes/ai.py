# app/routes/ai.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ai.ai_utils import predict_eligibility, classify_intent, EligibilityModelNotFound, IntentModelNotFound

router = APIRouter(prefix="/ai", tags=["ai"])

class EligIn(BaseModel):
    age:int; gender:str; income:int; education_years:int; rural:int; caste_marginalized:int

@router.post("/predict")
def predict(inp: EligIn):
    try:
        out = predict_eligibility(inp.model_dump())
        return {"label": out["label"], "confidence": out["prob"], "risk_score": out["risk_score"], "risk_flag": out["risk_flag"]}
    except EligibilityModelNotFound as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"eligibility error: {e}")

class IntentIn(BaseModel):
    text: str

@router.post("/classify")
def classify(inp: IntentIn):
    try:
        label, conf = classify_intent(inp.text)
        return {"label": label, "confidence": conf}
    except IntentModelNotFound as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"intent error: {e}")