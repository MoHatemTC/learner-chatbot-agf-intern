import os
import logging
import json
import sys
import pytz
from typing import Set, List, Dict
from datetime import datetime

# New import for environment variables
from dotenv import load_dotenv

from supabase import create_client, Client
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool

from datasets import Dataset
from ragas import evaluate
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall

from langchain_openai import OpenAIEmbeddings as LangchainOpenAIEmbeddings
from openai import OpenAI

# ---------------------------------------------------
# 0. LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------
load_dotenv()

# ---------------------------------------------------
# 1. CONFIG
# ---------------------------------------------------

CAIRO_TZ = pytz.timezone("Africa/Cairo")
UAE_TZ = pytz.timezone("Asia/Dubai")

# Pulling values from .env file
STATE_FILE = os.getenv("STATE_FILE", "sent_reminders.json")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Set the environment variable for CrewAI and OpenAI internal use
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ---------------------------------------------------
# 2. PERSISTENCE
# ---------------------------------------------------

def load_sent_ids() -> Set[int]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_sent_id(session_id: int):
    ids = load_sent_ids()
    ids.add(session_id)

    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)


# ---------------------------------------------------
# 3. TOOL
# ---------------------------------------------------

@tool("Circle_Post_Tool")
def circle_post_tool(reminder_text: str, session_id: int) -> str:
    """Publishes formatted reminders to the Circle community platform."""

    logging.info(f"🚀 Pushing Reminder to Circle for ID: {session_id}")

    print(f"\n📢 FINAL POST:\n{reminder_text}\n")

    save_sent_id(session_id)

    return "Successfully posted."


# ---------------------------------------------------
# 4. RAGAS EVALUATION
# ---------------------------------------------------

def run_ragas_evaluation(evaluation_data: List[Dict]):

    if not evaluation_data:
        print("No data found for evaluation.")
        return

    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    ragas_llm = llm_factory(
        "gpt-4o-mini",
        client=openai_client
    )

    ragas_embeddings = LangchainOpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=OPENAI_API_KEY
    )

    dataset_dict = {
        "question": [item["question"] for item in evaluation_data],
        "contexts": [[item["contexts"][0]] for item in evaluation_data],
        "answer": [item["answer"] for item in evaluation_data],
        "ground_truth": [item["ground_truth"] for item in evaluation_data],
    }

    hf_dataset = Dataset.from_dict(dataset_dict)

    print("\nStarting Ragas Evaluation...")

    result = evaluate(
        hf_dataset,
        metrics=[
            Faithfulness(),
            AnswerRelevancy(),
            ContextPrecision(),
            ContextRecall()
        ],
        llm=ragas_llm,
        embeddings=ragas_embeddings
    )

    print("\n--- Ragas Evaluation Results ---")
    print(result)

    df = result.to_pandas()
    df.to_csv("evaluation_report.csv", index=False)

    print("\nDetailed report saved to evaluation_report.csv")


# ---------------------------------------------------
# 5. CORE LOGIC
# ---------------------------------------------------

def fetch_data_from_supabase() -> List[Dict]:

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    now_cairo = datetime.now(CAIRO_TZ)
    today_cairo = now_cairo.strftime("%Y-%m-%d")

    logging.info(f"Checking Supabase for: {today_cairo}")

    try:
        res = supabase.table("schedule").select("*").eq("session_date", today_cairo).execute()
    except Exception as e:
        logging.error(f"DB Error: {e}")
        return []

    sent_ids = load_sent_ids()

    upcoming = [s for s in res.data if s["id"] not in sent_ids]

    if not upcoming:
        logging.info("⏭️ No new sessions.")
        return []

    evaluation_data = []

    crew_llm = LLM(model="gpt-4o-mini")

    coordinator = Agent(
        role="Strict Data Formatter",
        goal="Convert database rows to factual reminders. No filler.",
        backstory="Automated reminder pipeline.",
        tools=[circle_post_tool],
        verbose=True,
        llm=crew_llm
    )

    for session in upcoming:

        session_id = session["id"]

        time_str = session["session_time"].strip()
        date_str = str(session["session_date"])

        naive_dt = datetime.strptime(
            f"{date_str} {time_str}",
            "%Y-%m-%d %I:%M %p"
        )

        session_cairo = CAIRO_TZ.localize(naive_dt)

        session_uae = session_cairo.astimezone(UAE_TZ)

        uae_time_str = session_uae.strftime("%I:%M %p")

        factual_data = (
            f"Topic: {session.get('topic')}\n"
            f"Expert: {session.get('expert_name')}\n"
            f"Cairo Time: {time_str}\n"
            f"UAE Time: {uae_time_str}\n"
            f"Zoom Link: {session.get('zoom_link')}"
        )

        task = Task(
            description=f"Draft reminder using ONLY these facts:\n{factual_data}",
            expected_output="A list of the session facts provided.",
            agent=coordinator
        )

        crew = Crew(
            agents=[coordinator],
            tasks=[task]
        )

        result = str(crew.kickoff())

        evaluation_data.append({
            "question": f"What are the specific details for the session on {session.get('topic')}?",
            "contexts": [factual_data],
            "answer": result,
            "ground_truth": factual_data
        })

    return evaluation_data


# ---------------------------------------------------
# 6. MAIN
# ---------------------------------------------------

if __name__ == "__main__":

    # Note: Removing state file on start for a fresh run
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

    eval_data = fetch_data_from_supabase()

    if eval_data:
        run_ragas_evaluation(eval_data)
