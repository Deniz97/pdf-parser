from __future__ import annotations

from openai import OpenAI

SYSTEM_PROMPT = (
    "You are a helpful assistant. The user will provide a question and the text "
    "content extracted (via OCR) from a PDF document. Answer the question using "
    "only the information in the provided PDF text. "
    "Give only the answer with no extra explanation."
)

_FORMAT_HINTS: dict[str, str] = {
    "select": "\n\nThis is a Yes/No dropdown. Respond with ONLY 'Yes' or 'No'.",
    "text": "\n\nRespond with a short, precise answer.",
}


def ask(
    question: str,
    context: str,
    model: str = "gpt-4o-mini",
    answer_type: str = "text",
) -> str:
    """Send the question and PDF context to the OpenAI API and return the answer.

    *answer_type* can be ``'text'`` (free-form) or ``'select'`` (Yes/No
    dropdown) — a format hint is appended to steer the LLM response.
    """
    client = OpenAI()

    user_message = (
        f"### Question\n{question}\n\n"
        f"### PDF Content\n{context}"
        f"{_FORMAT_HINTS.get(answer_type, '')}"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content.strip()
