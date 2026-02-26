import os
from datasets import Dataset

from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI

from runner import ChatbotRunner


def extract_contexts(raw_results, max_chars=1500):
    """
    Converts your Qdrant search results into list[str] for RAGAS.
    Typical Qdrant point has: result.payload["text"].
    """
    contexts = []
    for r in raw_results or []:
        txt = ""
        if hasattr(r, "payload") and isinstance(r.payload, dict):
            txt = (r.payload.get("text") or "").strip()
        if txt:
            contexts.append(txt[:max_chars])
    return contexts


def main():
    # RAGAS uses an LLM for some metrics (use cheap + deterministic)
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    )

    # Put your real test questions here
    test_questions = [
    "Is the program online or offline?",
    "What are the program's fields?",
    "When will our live sessions be?",
    "What are the fees for the program?",
]

    runner = ChatbotRunner()

    rows = []
    for q in test_questions:
        out = runner.answer_question(q)
        rows.append(
            {
                "question": q,
                "answer": out.get("answer", ""),
                "contexts": extract_contexts(out.get("raw_results", [])),
            }
        )

    ds = Dataset.from_list(rows)

    results = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy],
        llm=evaluator_llm,
    )

    print("\n=== RAGAS (overall) ===")
    print(results)

    print("\n=== RAGAS (per question) ===")
    print(results.to_pandas())


if __name__ == "__main__":
    main()