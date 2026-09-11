from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.auth import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from backend.app.database import SessionLocal, get_db
from backend.app.models.user import User
from backend.app.schemas.auth import Token, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_USERS = [
    ("viewer1", "viewer123", ROLE_VIEWER),
    ("operator1", "operator123", ROLE_OPERATOR),
    ("admin1", "admin123", ROLE_ADMIN),
]


def _seed_users():
    db = SessionLocal()
    try:
        for username, password, role in DEMO_USERS:
            if db.query(User).filter(User.username == username).first() is None:
                db.add(User(username=username, hashed_password=hash_password(password), role=role))

        db.commit()
    finally:
        db.close()


_seed_users()


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(user.username, user.role)
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(ROLE_ADMIN)),
):
    return db.query(User).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(ROLE_ADMIN)),
):
    if db.query(User).filter(User.username == user_in.username).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        username=user_in.username,
        hashed_password=hash_password(user_in.password),
        role=user_in.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user
