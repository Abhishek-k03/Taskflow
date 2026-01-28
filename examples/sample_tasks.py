# examples/sample_tasks.py

import time
import random
from taskflow.core.registry import task


@task()
def hello_world(name: str = "World"):
    """Simple hello world task"""
    print(f"Hello, {name}!")
    return f"Greeted {name}"


@task()
def add_numbers(a: int, b: int):
    """Add two numbers"""
    result = a + b
    print(f"{a} + {b} = {result}")
    return result


@task()
def slow_task(duration: int = 5):
    """Simulate a slow task"""
    print(f"Starting slow task (will take {duration}s)...")
    time.sleep(duration)
    print("Slow task completed!")
    return f"Slept for {duration} seconds"


@task()
def random_failure(failure_rate: float = 0.3):
    """Task that randomly fails (useful for testing retries)"""
    if random.random() < failure_rate:
        raise Exception(f"Random failure occurred! (failure rate: {failure_rate})")
    return "Success!"


@task()
def process_data(data: list):
    """Process a list of data"""
    print(f"Processing {len(data)} items...")
    result = [item * 2 for item in data]
    time.sleep(1)  # Simulate processing time
    return result


@task()
def fetch_api_data(url: str):
    """Simulate fetching data from an API"""
    print(f"Fetching data from {url}...")
    time.sleep(2)  # Simulate network delay
    
    # In real scenario, you'd use requests library
    # For demo, return mock data
    return {
        "url": url,
        "status": 200,
        "data": {"message": "Mock API response"}
    }


@task()
def generate_report(report_type: str):
    """Generate a report"""
    print(f"Generating {report_type} report...")
    time.sleep(3)
    
    return {
        "report_type": report_type,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "completed"
    }


@task()
def send_email(to: str, subject: str, body: str):
    """Simulate sending an email"""
    print(f"Sending email to {to}")
    print(f"Subject: {subject}")
    time.sleep(1)
    
    # In real scenario, use smtplib or email service API
    return f"Email sent to {to}"


@task()
def cleanup_old_files(days_old: int = 30):
    """Simulate cleanup of old files"""
    print(f"Cleaning up files older than {days_old} days...")
    time.sleep(2)
    
    # In real scenario, scan filesystem and delete old files
    files_deleted = random.randint(0, 100)
    return f"Deleted {files_deleted} old files"


@task()
def database_backup():
    """Simulate database backup"""
    print("Starting database backup...")
    time.sleep(5)
    
    backup_size = random.randint(100, 1000)
    return f"Backup completed: {backup_size}MB"


# Import all tasks so they're registered when this module is imported
def register_all_tasks():
    """Convenience function to ensure all tasks are registered"""
    # Tasks are auto-registered via decorator, but this can be used
    # to verify or force registration
    from taskflow.core.registry import task_registry
    print(f"Registered tasks: {task_registry.list_tasks()}")


if __name__ == "__main__":
    register_all_tasks()