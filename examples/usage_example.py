# examples/usage_example.py

"""
Examples of how to use TaskFlow API
Run the server first: python main.py
Then run these examples in a separate terminal
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000/api/v1"


def submit_simple_task():
    """Submit a simple task"""
    print("\n=== Submitting Simple Task ===")
    
    response = requests.post(
        f"{BASE_URL}/tasks",
        json={
            "func_name": "hello_world",
            "args": ["TaskFlow User"],
            "priority": 2
        }
    )
    
    task = response.json()
    print(f"Task created: {task['task_id']}")
    print(f"Status: {task['status']}")
    return task['task_id']


def submit_task_with_kwargs():
    """Submit task with keyword arguments"""
    print("\n=== Submitting Task with Kwargs ===")
    
    response = requests.post(
        f"{BASE_URL}/tasks",
        json={
            "func_name": "add_numbers",
            "kwargs": {"a": 10, "b": 20},
            "priority": 1
        }
    )
    
    task = response.json()
    print(f"Task created: {task['task_id']}")
    return task['task_id']


def submit_slow_task():
    """Submit a task that takes time"""
    print("\n=== Submitting Slow Task ===")
    
    response = requests.post(
        f"{BASE_URL}/tasks",
        json={
            "func_name": "slow_task",
            "args": [3],  # Sleep for 3 seconds
            "timeout": 10,  # 10 second timeout
        }
    )
    
    task = response.json()
    print(f"Task created: {task['task_id']}")
    return task['task_id']


def check_task_status(task_id):
    """Check task status"""
    print(f"\n=== Checking Task {task_id} ===")
    
    response = requests.get(f"{BASE_URL}/tasks/{task_id}")
    task = response.json()
    
    print(f"Status: {task['status']}")
    print(f"Result: {task['result']}")
    print(f"Error: {task['error']}")
    print(f"Retry count: {task['retry_count']}")
    
    return task


def wait_for_task_completion(task_id, timeout=30):
    """Poll task until it completes"""
    print(f"\n=== Waiting for Task {task_id} ===")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        task = check_task_status(task_id)
        
        if task['status'] in ['completed', 'failed']:
            print(f"\nTask finished with status: {task['status']}")
            return task
        
        print(".", end="", flush=True)
        time.sleep(1)
    
    print(f"\nTimeout waiting for task")
    return None


def list_all_tasks():
    """List all tasks"""
    print("\n=== All Tasks ===")
    
    response = requests.get(f"{BASE_URL}/tasks")
    tasks = response.json()
    
    for task in tasks:
        print(f"{task['task_id'][:8]}... | {task['func_name']:20} | {task['status']:10} | {task['result']}")


def create_periodic_task():
    """Create a periodic task"""
    print("\n=== Creating Periodic Task ===")
    
    response = requests.post(
        f"{BASE_URL}/periodic-tasks",
        json={
            "name": "daily_cleanup",
            "func_name": "cleanup_old_files",
            "cron_expression": "0 2 * * *",  # Every day at 2 AM
            "kwargs": {"days_old": 30}
        }
    )
    
    result = response.json()
    print(result['message'])


def create_test_periodic_task():
    """Create a periodic task that runs every minute (for testing)"""
    print("\n=== Creating Test Periodic Task ===")
    
    response = requests.post(
        f"{BASE_URL}/periodic-tasks",
        json={
            "name": "test_task",
            "func_name": "hello_world",
            "cron_expression": "* * * * *",  # Every minute
            "args": ["Periodic Task"]
        }
    )
    
    result = response.json()
    print(result['message'])


def list_periodic_tasks():
    """List all periodic tasks"""
    print("\n=== Periodic Tasks ===")
    
    response = requests.get(f"{BASE_URL}/periodic-tasks")
    tasks = response.json()
    
    for name, info in tasks.items():
        print(f"\nName: {name}")
        print(f"  Function: {info['func_name']}")
        print(f"  Schedule: {info['cron_expression']}")
        print(f"  Next run: {info['next_run']}")
        print(f"  Run count: {info['run_count']}")


def trigger_periodic_task(name):
    """Manually trigger a periodic task"""
    print(f"\n=== Triggering Periodic Task: {name} ===")
    
    response = requests.post(f"{BASE_URL}/periodic-tasks/{name}/trigger")
    result = response.json()
    
    print(result['message'])
    print(f"Task ID: {result['task_id']}")
    return result['task_id']


def get_system_metrics():
    """Get system metrics"""
    print("\n=== System Metrics ===")
    
    response = requests.get(f"{BASE_URL}/metrics")
    metrics = response.json()
    
    print(json.dumps(metrics, indent=2))


def list_registered_tasks():
    """List all registered task functions"""
    print("\n=== Registered Task Functions ===")
    
    response = requests.get(f"{BASE_URL}/registered-tasks")
    tasks = response.json()
    
    print(f"Available tasks: {', '.join(tasks['tasks'])}")


def demo_workflow():
    """Demo complete workflow"""
    print("\n" + "="*50)
    print("TASKFLOW DEMO")
    print("="*50)
    
    # 1. List registered tasks
    list_registered_tasks()
    
    # 2. Submit various tasks
    task1 = submit_simple_task()
    task2 = submit_task_with_kwargs()
    task3 = submit_slow_task()
    
    # 3. Wait for tasks to complete
    print("\nWaiting for tasks to complete...")
    time.sleep(5)
    
    # 4. Check results
    list_all_tasks()
    
    # 5. Create periodic task
    create_test_periodic_task()
    list_periodic_tasks()
    
    # 6. Show metrics
    get_system_metrics()
    
    print("\n" + "="*50)
    print("Demo complete!")
    print("="*50)


if __name__ == "__main__":
    # Run the demo
    try:
        demo_workflow()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to TaskFlow server.")
        print("Make sure the server is running: python main.py")