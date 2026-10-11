from google_antigravity import Agent
import time

def main():
    agent = Agent("Wait for feedback")
    plan = agent.create_artifact("plan.md", "This is a plan.", request_feedback=True)
    print("Feedback requested.")
    time.sleep(10)

if __name__ == "__main__":
    main()
