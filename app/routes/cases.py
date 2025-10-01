from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from .. import models, schemas
from ..db import get_db

router = APIRouter(prefix="/cases", tags=["cases"])

@router.post("/", response_model=schemas.CaseResponse, status_code=201)
def create_case(case: schemas.CaseCreate, db: Session = Depends(get_db)):
    scheme = db.query(models.Scheme).filter(models.Scheme.code == case.scheme_code).first()
    if not scheme:
        raise HTTPException(status_code=400, detail="Invalid scheme_code")
    new_case = models.Case(
        citizen_hash=case.citizen_hash,
        scheme_code=case.scheme_code,
        source=case.source,
        locale=case.locale,
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    db.add(models.Event(
        case_id=new_case.id,
        action=models.ActionEnum.CREATE_CASE,
        actor_type="CITIZEN",
        payload='{}'
    ))
    db.commit()

    return new_case

@router.get("/{case_id}", response_model=schemas.CaseResponse)
def get_case(case_id: str, db: Session = Depends(get_db)):
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Case not found")
    return obj

@router.patch("/{case_id}/status")
def update_status(
    case_id: str,
    status: str = Query(..., description="NEW | IN_REVIEW | APPROVED | REJECTED"),
    db: Session = Depends(get_db)
):
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Case not found")
    valid = [s.value for s in models.StatusEnum]
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {valid}")
    obj.status = status
    db.commit()
    db.refresh(obj)

    db.add(models.Event(
        case_id=obj.id,
        action=models.ActionEnum.UPDATE_STATUS,
        actor_type="OPERATOR",
        payload="{}"
    ))
    db.commit()
    return {"ok": True}