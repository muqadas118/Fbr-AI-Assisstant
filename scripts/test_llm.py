from app.llm import generate_answer


def main():
    print("=" * 60)
    print("FBR LLM TEST")
    print("=" * 60)

    question = "What is income tax?"

    context = """
    Income Tax Ordinance, 2001.

    Section 11 states that for purposes of imposition of tax
    and computation of total income, income is classified under
    the following heads:

    (a) Salary
    (b) Income from Property
    (c) Income from Business
    (d) Capital Gains
    (e) Income from Other Sources.
    """

    print(f"Question: {question}")
    print()
    print("Generating answer...")
    print()

    answer = generate_answer(question, context)

    print("=" * 60)
    print("ANSWER")
    print("=" * 60)
    print(answer)
    print("=" * 60)


if __name__ == "__main__":
    main()