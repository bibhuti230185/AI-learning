"""Exercise 2: Creating and Using a JSON Output Parser.

This exercise demonstrates how to:
1. Create a JSON output parser with structured Pydantic models
2. Build a chain that connects prompt, LLM, and parser
3. Test parsing with multiple inputs
4. Access specific fields from parsed JSON output
"""

from pydantic import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from session1_shared import (
    DEFAULT_MAX_TOKENS,
    AVAILABLE_MODELS,
    build_chat_model,
    get_api_key_or_exit,
    get_available_chat_models,
    select_primary_secondary_models,
    setup_runtime,
)


class Movie(BaseModel):
    """Structured representation of a movie."""

    title: str = Field(description="movie title")
    director: str = Field(description="director name")
    year: int = Field(description="release year")
    genre: str = Field(description="movie genre")


def run() -> None:
    setup_runtime(__file__)

    api_key = get_api_key_or_exit()
    chat_models = get_available_chat_models()
    model_primary, _ = select_primary_secondary_models(chat_models)

    print(f"Selected model: {model_primary}")
    print("Available models:")
    for model_name, metadata in AVAILABLE_MODELS.items():
        print(
            f"  - {model_name} | usage={metadata['usage']} | max_tokens={metadata['max_tokens']} | license={metadata['license']}"
        )

    llm = build_chat_model(model_primary, api_key, temperature=0.1, max_tokens=DEFAULT_MAX_TOKENS)

    print("\n" + "=" * 80)
    print("EXERCISE 2: Creating and Using a JSON Output Parser")
    print("=" * 80)

    # Create JSON parser from the Movie model
    json_parser = JsonOutputParser(pydantic_object=Movie)
    format_instructions = json_parser.get_format_instructions()

    # Create prompt template with format instructions
    prompt_template = PromptTemplate(
        template="""You are a JSON-only assistant that returns structured movie information.

Task: Generate detailed information about the movie "{movie_name}" in JSON format.

{format_instructions}

Ensure your response is ONLY valid JSON matching the required structure. Do NOT include any markdown, explanations, or extra text.""",
        input_variables=["movie_name"],
        partial_variables={"format_instructions": format_instructions},
    )

    # Create the chain: prompt → LLM → JSON parser
    movie_chain = prompt_template | llm | json_parser

    # Test with multiple movie names
    test_movies = [
        "The Matrix",
        "Inception",
        "Pulp Fiction",
    ]

    for movie_name in test_movies:
        print("\n" + "-" * 80)
        print(f"Processing: {movie_name}")
        print("-" * 80)

        try:
            result = movie_chain.invoke({"movie_name": movie_name})

            print(f"Parsed result (type: {type(result).__name__}):")
            print(f"  Title:    {result['title']}")
            print(f"  Director: {result['director']}")
            print(f"  Year:     {result['year']}")
            print(f"  Genre:    {result['genre']}")

            # Demonstrate that result is a proper Python dictionary
            print(f"\nDictionary access examples:")
            print(f"  result.get('title'):    {result.get('title')}")
            print(f"  result.get('year'):     {result.get('year')}")
            print(f"  dict keys:              {list(result.keys())}")

        except Exception as e:
            print(f"Error processing {movie_name}: {e}")

    print("\n" + "=" * 80)
    print("Exercise 2 observations:")
    print("- JsonOutputParser enforces the Pydantic schema structure")
    print("- Format instructions guide the LLM to return valid JSON")
    print("- Parsed output is a native Python dictionary for easy access")
    print("- You can validate/transform output using Pydantic models")
    print("=" * 80)


if __name__ == "__main__":
    run()
