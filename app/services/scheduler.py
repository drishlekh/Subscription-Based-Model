# app/services/scheduler.py
import schedule
import time
import threading
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..crud import get_subscriptions_to_expire, update_subscription_status
from ..models import SubscriptionStatusEnum

def expire_subscriptions_job():
    """
    Why this function is necessary:
    - This is the core logic for the background task that handles subscription expiration.
    - It needs to run periodically to check for and update expired subscriptions.
    What it's doing:
    - Creates its own database session because it runs in a separate thread.
    - Calls `crud.get_subscriptions_to_expire` to find subscriptions that should be expired.
    - For each such subscription, it calls `crud.update_subscription_status` to set its
      status to `SubscriptionStatusEnum.EXPIRED`.
    - Prints a log message for each updated subscription.
    - Ensures the database session is closed.
    """
    print("Scheduler: Running expire_subscriptions_job...")
    db: Session = SessionLocal()
    try:
        subscriptions_to_expire = get_subscriptions_to_expire(db)
        if not subscriptions_to_expire:
            print("Scheduler: No subscriptions to expire.")
            return

        for sub in subscriptions_to_expire:
            print(f"Scheduler: Expiring subscription ID {sub.id} for user ID {sub.user_id}")
            update_subscription_status(db, sub.id, SubscriptionStatusEnum.EXPIRED)
        print(f"Scheduler: Processed {len(subscriptions_to_expire)} subscriptions for expiration.")
    except Exception as e:
        print(f"Scheduler: Error during expire_subscriptions_job: {e}")
    finally:
        db.close()

def run_scheduler():
    """
    Why this function is necessary:
    - To set up and run the `schedule` library's event loop.
    - This function will run in a separate thread so it doesn't block the main FastAPI application.
    What it's doing:
    - Enters an infinite loop (`while True`).
    - `schedule.run_pending()`: Checks if any scheduled jobs are due to run and executes them.
    - `time.sleep(1)`: Pauses for 1 second before checking again. This determines the granularity
      of the scheduler (how often it checks if a job is due).
    """
    while True:
        schedule.run_pending()
        time.sleep(60) # Check every 60 seconds

def start_background_scheduler():
    """
    Why this function is necessary:
    - To configure the schedule for the `expire_subscriptions_job` and start the scheduler
      in a background thread.
    - This is typically called once when the FastAPI application starts up.
    What it's doing:
    - `schedule.every().day.at("01:00").do(expire_subscriptions_job)`: Configures the
      `expire_subscriptions_job` to run every day at 1:00 AM. You can change this to
      `schedule.every(1).minutes.do(expire_subscriptions_job)` for more frequent testing.
    - Creates a new thread (`threading.Thread`) that will run the `run_scheduler` function.
    - `daemon=True`: Makes the thread a daemon thread, meaning it will exit automatically
      when the main program exits.
    - `scheduler_thread.start()`: Starts the background thread.
    """
    # Schedule the job. For testing, you might want it to run more frequently.
    # e.g., schedule.every(1).minutes.do(expire_subscriptions_job)
    schedule.every().day.at("01:00").do(expire_subscriptions_job) # Run daily at 1 AM
    # For demonstration, let's run it every 5 minutes
    # schedule.every(5).minutes.do(expire_subscriptions_job)
    print("Scheduler: Background scheduler configured. Expiration job will run as scheduled.")

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("Scheduler: Background scheduler thread started.")