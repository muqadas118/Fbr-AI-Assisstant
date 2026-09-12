import re


MIN_RETRIEVAL_SCORE = 0.45
MIN_CONTEXT_LENGTH = 40


def verify_retrieval(results):
    """
    Check whether retrieved FBR context is strong enough
    to support an answer.
    """

    if not results:
        return {
            "passed": False,
            "reason": "No documents were retrieved.",
        }

    valid_results = []

    for result in results:
        score = float(result.get("score", 0))
        text = str(result.get("text", "")).strip()

        if score >= MIN_RETRIEVAL_SCORE and len(text) >= MIN_CONTEXT_LENGTH:
            valid_results.append(result)

    if not valid_results:
        return {
            "passed": False,
            "reason": "Retrieved documents were too weak or empty.",
        }

    return {
        "passed": True,
        "reason": "Sufficient FBR context retrieved.",
        "valid_results": valid_results,
    }


def verify_answer(answer, results):
    """
    Basic grounding verification.

    The answer must:
    - exist
    - not claim unsupported information when context is empty
    - have supporting retrieved context
    """

    answer = (answer or "").strip()

    retrieval_check = verify_retrieval(results)

    if not retrieval_check["passed"]:
        return {
            "passed": False,
            "reason": retrieval_check["reason"],
            "answer": "",
        }

    if not answer:
        return {
            "passed": False,
            "reason": "LLM returned an empty answer.",
            "answer": "",
        }

    weak_phrases = [
        "i don't know",
        "i cannot answer",
        "not enough information",
        "do not contain enough information",
        "cannot determine",
    ]

    answer_lower = answer.lower()

    if any(phrase in answer_lower for phrase in weak_phrases):
        return {
            "passed": False,
            "reason": "LLM produced an unsupported or insufficient answer.",
            "answer": "",
        }

    return {
        "passed": True,
        "reason": "Answer passed basic grounding verification.",
        "answer": answer,
        "sources": [
            {
                "source": item.get("source"),
                "chunk_id": item.get("chunk_id"),
                "score": item.get("score"),
            }
            for item in retrieval_check["valid_results"]
        ],
    }


def build_context(results, max_results=5):
    """
    Build clean context for the LLM from retrieved results.
    """

    verified = verify_retrieval(results)

    if not verified["passed"]:
        return ""

    context_parts = []

    for index, result in enumerate(
        verified["valid_results"][:max_results],
        start=1,
    ):
        source = result.get("source", "Unknown source")
        score = result.get("score", 0)
        text = result.get("text", "").strip()

        context_parts.append(
            f"[SOURCE {index}]\n"
            f"Document: {source}\n"
            f"Similarity: {score:.4f}\n"
            f"Content:\n{text}"
        )

    return "\n\n".join(context_parts)