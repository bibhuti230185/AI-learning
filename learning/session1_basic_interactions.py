"""Run basic single-turn and multi-turn interactions for Session 1."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from session1_shared import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_chat_model,
    get_api_key_or_exit,
    get_available_chat_models,
    select_primary_secondary_models,
    setup_runtime,
)


def run() -> None:
    setup_runtime(__file__)

    api_key = get_api_key_or_exit()
    chat_models = get_available_chat_models()
    model_primary, model_secondary = select_primary_secondary_models(chat_models)
    print(f"Selected models: primary={model_primary}, secondary={model_secondary}")

    llm = build_chat_model(
        model_name=model_primary,
        api_key=api_key,
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=DEFAULT_MAX_TOKENS,
    )

    print("=" * 80)
    print("Example 1: Simple Question")
    print("=" * 80)
    response = llm.invoke("Who is man's best friend?")
    print(f"Response: {response.content}\n")

    print("=" * 80)
    print("Example 2: Question with System Context (Book Recommendation)")
    print("=" * 80)
    response = llm.invoke(
        [
            SystemMessage(
                content="You are a helpful AI bot that assists a user in choosing the perfect book to read in one short sentence"
            ),
            HumanMessage(content="I enjoy mystery novels, what should I read?"),
        ]
    )
    print(f"Response: {response.content}\n")

    print("=" * 80)
    print("Example 3: Multi-Turn Conversation (Fitness Recommendations)")
    print("=" * 80)
    response = llm.invoke(
        [
            SystemMessage(
                content="You are a supportive AI bot that suggests fitness activities to a user in one short sentence"
            ),
            HumanMessage(content="I like high-intensity workouts, what should I do?"),
            AIMessage(content="You should try a CrossFit class"),
            HumanMessage(content="How often should I attend?"),
        ]
    )
    print(f"Response: {response.content}\n")

    print("=" * 80)
    print("Example 4: Factual Question")
    print("=" * 80)
    response = llm.invoke([HumanMessage(content="What month follows June?")])
    print(f"Response: {response.content}\n")


if __name__ == "__main__":
    run()
