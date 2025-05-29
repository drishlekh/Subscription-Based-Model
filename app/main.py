# app/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Path
from fastapi.security import OAuth2PasswordRequestForm # For login form data
from sqlalchemy.orm import Session
from sqlalchemy.exc import MultipleResultsFound
from typing import List
from datetime import timedelta
from fastapi.responses import PlainTextResponse

from . import crud, models, schemas
from .database import engine, get_db, SessionLocal
from .services.scheduler import start_background_scheduler
from .auth import ( # Import auth functions
    create_access_token,
    get_current_active_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    verify_password
)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="User Subscription Service API",
    description="API for managing user subscriptions and plans, with JWT authentication.",
    version="1.1.0"
)

@app.on_event("startup")
async def startup_event():
    print("Application startup: Initializing...")
    start_background_scheduler()
    seed_initial_plans()
    print("Application startup: Complete.")

def seed_initial_plans():
    db: Session = SessionLocal()
    try:
        if db.query(models.Plan).count() == 0:
            print("Seeding initial plans...")
            plans_to_seed = [
                schemas.PlanCreate(name="Free Trial", price=0.00, features="Limited access, 7 days", duration_days=7),
                schemas.PlanCreate(name="Basic", price=9.99, features="Access to basic features, monthly", duration_days=30),
                schemas.PlanCreate(name="Premium", price=19.99, features="Access to all features, priority support, monthly", duration_days=30),
                schemas.PlanCreate(name="Pro Yearly", price=199.99, features="All premium features, yearly discount", duration_days=365),
            ]
            for plan_data in plans_to_seed:
                crud.create_plan(db=db, plan=plan_data)
            print(f"Seeded {len(plans_to_seed)} plans.")
        else:
            print("Plans already exist, skipping seeding.")
    finally:
        db.close()

# --- Authentication Endpoint ---
@app.post("/token", response_model=schemas.Token, tags=["Authentication"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Why this endpoint is necessary:
    - Allows users to exchange their username and password for a JWT access token.
    What it's doing:
    1. Takes username and password from the form data (`OAuth2PasswordRequestForm`).
    2. Fetches the user from the database by username.
    3. If user not found or password incorrect, raises an authentication error.
    4. If credentials are valid, creates a new JWT access token.
    5. Returns the token.
    """
    user = crud.get_user_by_username(db, username=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- User Endpoints ---
@app.post("/users/", response_model=schemas.User, status_code=status.HTTP_201_CREATED, tags=["Users"])
def create_new_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Creates a new user. The password provided will be hashed.
    This endpoint is typically public.
    """
    db_user_by_email = crud.get_user_by_email(db, email=user.email)
    if db_user_by_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user_by_username = crud.get_user_by_username(db, username=user.username)
    if db_user_by_username:
        raise HTTPException(status_code=400, detail="Username already registered")
    return crud.create_user(db=db, user=user)

@app.get("/users/me/", response_model=schemas.User, tags=["Users"])
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """
    Why this endpoint is necessary:
    - Allows an authenticated user to retrieve their own user details.
    What it's doing:
    - Relies on `get_current_active_user` to ensure the request is authenticated.
    - Returns the details of the currently logged-in user.
    """
    return current_user

# --- Plan Endpoints ---
@app.post("/plans/", response_model=schemas.Plan, status_code=status.HTTP_201_CREATED, tags=["Plans"])
def create_new_plan(
    plan: schemas.PlanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Protected
):
    """
    Creates a new subscription plan. Requires authentication.
    (You might want admin-only access for this in a real app).
    """
    existing_plan = db.query(models.Plan).filter(models.Plan.name == plan.name).first()
    if existing_plan:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Plan with name '{plan.name}' already exists.")
    return crud.create_plan(db=db, plan=plan)

@app.get("/plans/", response_model=List[schemas.Plan], tags=["Plans"])
def read_all_available_plans(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieves all available plans. This endpoint can remain public.
    """
    plans = crud.get_plans(db, skip=skip, limit=limit)
    return plans

# --- Subscription Endpoints ---
@app.post("/subscriptions/", response_model=schemas.Subscription, status_code=status.HTTP_201_CREATED, tags=["Subscriptions"])
def create_new_subscription(
    subscription_in: schemas.SubscriptionCreate, # Client now only sends plan_id
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Protected
):
    """
    Allows an authenticated user to subscribe to a specific plan.
    The user_id is derived from the authentication token.
    """
    db_plan = crud.get_plan(db, plan_id=subscription_in.plan_id)
    if not db_plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Plan with ID {subscription_in.plan_id} not found.")

    # user_id comes from current_user (the authenticated user)
    user_id_from_token = current_user.id
    active_subscription = crud.get_active_subscription_by_user(db, user_id=user_id_from_token)
    if active_subscription:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User {current_user.username} already has an active subscription (ID: {active_subscription.id})."
        )
    try:
        # Pass user_id from token and plan_id from request
        new_subscription = crud.create_subscription(
            db=db,
            user_id=user_id_from_token,
            plan_id=subscription_in.plan_id,
            plan_details=db_plan
        )
        return new_subscription
    except MultipleResultsFound:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Data integrity issue: Multiple active subscriptions found unexpectedly.")


@app.get("/subscriptions/me/", response_model=schemas.Subscription, tags=["Subscriptions"])
def retrieve_my_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Protected
):
    """
    Retrieves the active subscription for the currently authenticated user.
    """
    try:
        active_subscription = crud.get_active_subscription_by_user(db, user_id=current_user.id)
    except MultipleResultsFound:
        print(f"CRITICAL: Multiple active subscriptions found for user_id {current_user.id} during GET request.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Multiple active subscriptions found for user. Please contact support.")

    if not active_subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active subscription found for user {current_user.username}.")
    return active_subscription


@app.put("/subscriptions/me/", response_model=schemas.Subscription, tags=["Subscriptions"])
def update_my_subscription(
    update_data: schemas.SubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Protected
):
    """
    Allows an authenticated user to update their active subscription plan.
    """
    active_subscription = crud.get_active_subscription_by_user(db, user_id=current_user.id)
    if not active_subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active subscription found for user {current_user.username} to update.")

    new_plan = crud.get_plan(db, plan_id=update_data.new_plan_id)
    if not new_plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"New plan with ID {update_data.new_plan_id} not found.")

    if active_subscription.plan_id == new_plan.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already subscribed to this plan.")

    updated_subscription = crud.update_subscription_plan(db, current_subscription=active_subscription, new_plan=new_plan)
    return updated_subscription


@app.delete("/subscriptions/me/", status_code=status.HTTP_204_NO_CONTENT, tags=["Subscriptions"])
def cancel_my_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Protected
):
    """
    Allows an authenticated user to cancel their active subscription.
    """
    active_subscription = crud.get_active_subscription_by_user(db, user_id=current_user.id)
    if not active_subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active subscription found for user {current_user.username} to cancel.")

    if active_subscription.status == models.SubscriptionStatusEnum.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription is already cancelled.")

    crud.cancel_subscription(db, subscription=active_subscription)
    return None


@app.get("/", response_class=PlainTextResponse, include_in_schema=False)
async def root():
    message = """
Welcome to the User Subscription Service API!

This is the root of the API. To explore and test the available endpoints:

--- OpenAPI (Swagger) Documentation:
   Open your browser and go to: /docs
   (e.g., http://127.0.0.1:8000/docs if running locally)

OR

--- Using Postman or other API clients:
   You can make requests to the specific API endpoints documented in /docs.
   Remember to include any necessary authentication (e.g., JWT Bearer token in the
   'Authorization' header for protected routes after logging in via the /token endpoint).

Available main functionalities:
- User registration: POST /users/
- User login (get JWT token): POST /token
- Manage plans (requires auth): GET /plans/, POST /plans/
- Manage subscriptions (requires auth): POST /subscriptions/me/, GET /subscriptions/me/, etc.

Happy testing!
    """
    return PlainTextResponse(content=message)