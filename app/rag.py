from app.llm import generate_answer
from app.retriever import FBRRetriever


class FBRRAG:

    def __init__(self, top_k=5):
        self.retriever = FBRRetriever()
        self.top_k = top_k

    def answer(self, question):

        results = self.retriever.search(
            question,
            top_k=self.top_k,
        )

        if not results:
            return {
                "answer": (
                    "The provided FBR documents do not contain "
                    "enough information to answer this."
                ),
                "sources": [],
            }

        context_parts = []

        for i, result in enumerate(results, start=1):

            context_parts.append(
                f"""
SOURCE {i}
Document: {result["source"]}
Chunk ID: {result["chunk_id"]}
Similarity Score: {result["score"]:.4f}

{result["text"]}
"""
            )

        context = "\n".join(context_parts)

        answer = generate_answer(
            question=question,
            context=context,
        )

        sources = []

        for result in results:
            sources.append(
                {
                    "source": result["source"],
                    "chunk_id": result["chunk_id"],
                    "score": result["score"],
                }
            )

        return {
            "answer": answer,
            "sources": sources,
        }