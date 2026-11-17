
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_roles
from app.models import Program, User
from app.schemas.program import ProgramCreate, ProgramResponse


router = APIRouter(prefix="/programs", tags=["Programs"])


@router.get("/", response_model=list[ProgramResponse])
def get_programs(db: Session = Depends(get_db)):
    return db.query(Program).filter(
        Program.is_active.is_(True)
    ).order_by(Program.name).all()


@router.post("/", response_model=ProgramResponse, status_code=201)
def create_program(
    data: ProgramCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    existing = db.query(Program).filter(
        Program.name == data.name
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="A program with this name already exists"
        )

    program = Program(**data.model_dump())

    db.add(program)
    db.commit()
    db.refresh(program)

    return program
