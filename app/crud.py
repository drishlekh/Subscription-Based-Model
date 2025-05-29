# app/crud.py
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound, MultipleResultsFound, SQLAlchemyError
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from . import models, schemas
from .auth import get_password_hash # Import the hashing function
from datetime import date, timedelta

db_retry_decorator = retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    retry=retry_if_exception_type(SQLAlchemyError)
)

# --- User CRUD ---
def get_user(db: Session, user_id: int) -> models.User | None:
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_username(db: Session, username: str) -> models.User | None:
    """
    Why this function is necessary:
    - To retrieve a user from the database by their username.
    - Primarily used during the login process to find the user attempting to authenticate.
    What it's doing:
    - Queries the 'users' table for a user with the given `username`.
    """
    return db.query(models.User).filter(models.User.username == username).first()

@db_retry_decorator
def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """
    Why this function is necessary:
    - To create a new user record, now with password hashing.
    What it's doing:
    - Hashes the plain-text password from `user.password` using `get_password_hash`.
    - Creates a new `models.User` instance with the username, email, and the `hashed_password`.
    - Saves to the database.
    """
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password # Store the hashed password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# --- Plan CRUD (no changes here) ---
def get_plan(db: Session, plan_id: int) -> models.Plan | None:
    return db.query(models.Plan).filter(models.Plan.id == plan_id).first()

def get_plans(db: Session, skip: int = 0, limit: int = 100) -> list[models.Plan]:
    return db.query(models.Plan).offset(skip).limit(limit).all()

@db_retry_decorator
def create_plan(db: Session, plan: schemas.PlanCreate) -> models.Plan:
    db_plan = models.Plan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan

# --- Subscription CRUD ---
def get_active_subscription_by_user(db: Session, user_id: int) -> models.Subscription | None:
    try:
        return db.query(models.Subscription).filter(
            models.Subscription.user_id == user_id,
            models.Subscription.status == models.SubscriptionStatusEnum.ACTIVE
        ).one_or_none()
    except MultipleResultsFound:
        print(f"Error: Multiple active subscriptions found for user_id {user_id}")
        raise

@db_retry_decorator
def create_subscription(db: Session, user_id: int, plan_id: int, plan_details: models.Plan) -> models.Subscription:
    """
    Updated to take user_id and plan_id directly, and plan_details object
    """
    start_date = date.today()
    end_date = start_date + timedelta(days=plan_details.duration_days)
    db_subscription = models.Subscription(
        user_id=user_id,
        plan_id=plan_id,
        start_date=start_date,
        end_date=end_date,
        status=models.SubscriptionStatusEnum.ACTIVE
    )
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription

@db_retry_decorator
def update_subscription_plan(db: Session, current_subscription: models.Subscription, new_plan: models.Plan) -> models.Subscription:
    current_subscription.plan_id = new_plan.id
    current_subscription.end_date = date.today() + timedelta(days=new_plan.duration_days)
    db.commit()
    db.refresh(current_subscription)
    return current_subscription

@db_retry_decorator
def cancel_subscription(db: Session, subscription: models.Subscription) -> models.Subscription:
    subscription.status = models.SubscriptionStatusEnum.CANCELLED
    db.commit()
    db.refresh(subscription)
    return subscription

def get_subscriptions_to_expire(db: Session) -> list[models.Subscription]:
    today = date.today()
    return db.query(models.Subscription).filter(
        models.Subscription.status == models.SubscriptionStatusEnum.ACTIVE,
        models.Subscription.end_date <= today
    ).all()

@db_retry_decorator
def update_subscription_status(db: Session, subscription_id: int, new_status: models.SubscriptionStatusEnum) -> models.Subscription | None:
    db_subscription = db.query(models.Subscription).filter(models.Subscription.id == subscription_id).first()
    if db_subscription:
        db_subscription.status = new_status
        db.commit()
        db.refresh(db_subscription)
    return db_subscription