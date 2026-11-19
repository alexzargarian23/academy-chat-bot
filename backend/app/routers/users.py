from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models import User, ApplicantLead
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token, EmailCheckRequest
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/check-email")
def check_email(data: EmailCheckRequest, db: Session = Depends(get_db)):
    """Email-first sign-in helper. Apply rate limiting before public production use."""
    exists = db.query(User.id).filter(User.email == str(data.email).lower()).first() is not None
    return {"registered": exists}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    email = str(user_data.email).lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    new_user = User(
        full_name=user_data.full_name.strip(),
        email=email,
        password_hash=hash_password(user_data.password),
        role="guest",
    )
    db.add(new_user)
    db.flush()

    # Every public student account starts one linked lead. A later AI conversation
    # enriches this same record rather than creating another lead.
    lead = ApplicantLead(
        user_id=new_user.id,
        full_name=new_user.full_name,
        email=new_user.email,
        phone="",
        source="website_registration",
        status="new",
        contact_consent=False,
        message="Account created on the Academy website.",
    )
    db.add(lead)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    email = str(user_data.email).lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user
