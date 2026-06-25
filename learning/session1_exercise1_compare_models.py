"""Run Exercise 1: compare two chat models at two temperature settings."""

from session1_shared import (
    DEFAULT_MAX_TOKENS,
    AVAILABLE_MODELS,
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
    print("Available models:")
    for model_name, metadata in AVAILABLE_MODELS.items():
        print(
            f"- {model_name} | usage={metadata['usage']} | max_tokens={metadata['max_tokens']} | license={metadata['license']}"
        )

    llm_primary_creative = build_chat_model(model_primary, api_key, temperature=0.8, max_tokens=DEFAULT_MAX_TOKENS)
    llm_primary_precise = build_chat_model(model_primary, api_key, temperature=0.1, max_tokens=DEFAULT_MAX_TOKENS)
    llm_secondary_creative = build_chat_model(model_secondary, api_key, temperature=0.8, max_tokens=DEFAULT_MAX_TOKENS)
    llm_secondary_precise = build_chat_model(model_secondary, api_key, temperature=0.1, max_tokens=DEFAULT_MAX_TOKENS)

    print("\n" + "=" * 80)
    print("EXERCISE 1: Compare Responses Across Two Models")
    print("=" * 80)

    test_prompts = {
        "Creative writing": "Write a short poem about artificial intelligence.",
        "Factual question": "What are the key components of a neural network?",
        "Instruction-following": "List 5 tips for effective time management.",
    }

    for prompt_type, prompt in test_prompts.items():
        print("\n" + "-" * 80)
        print(f"Prompt type: {prompt_type}")
        print(f"Prompt: {prompt}")

        primary_creative_response = llm_primary_creative.invoke(prompt)
        primary_precise_response = llm_primary_precise.invoke(prompt)
        secondary_creative_response = llm_secondary_creative.invoke(prompt)
        secondary_precise_response = llm_secondary_precise.invoke(prompt)

        print(f"\n{model_primary} (temperature = 0.8):")
        print(primary_creative_response.content)

        print(f"\n{model_primary} (temperature = 0.1):")
        print(primary_precise_response.content)

        print(f"\n{model_secondary} (temperature = 0.8):")
        print(secondary_creative_response.content)

        print(f"\n{model_secondary} (temperature = 0.1):")
        print(secondary_precise_response.content)

    print("\n" + "=" * 80)
    print("Exercise 1 observations:")
    print("- Higher temperature responses are usually more expressive and varied.")
    print("- Lower temperature responses are usually more concise and consistent.")
    print("- Model choice changes tone, structure, and level of detail.")
    print("=" * 80)


if __name__ == "__main__":
    run()
