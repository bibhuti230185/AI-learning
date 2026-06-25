"""PromptTemplate and ChatPromptTemplate examples with a runnable LLM chain."""

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from pydantic import BaseModel, Field

from session1_shared import (
	DEFAULT_MAX_TOKENS,
	DEFAULT_TEMPERATURE,
	build_chat_model,
	get_api_key_or_exit,
	get_available_chat_models,
	select_primary_secondary_models,
	setup_runtime,
)


class Joke(BaseModel):
	setup: str = Field(description="question to set up a joke")
	punchline: str = Field(description="answer to resolve the joke")


def run_structured_output_example(llm) -> None:
	"""Demonstrate structured JSON output parsing with JsonOutputParser."""
	joke_query = "Tell me a joke."

    # Define a prompt that instructs the model to output a joke in a structured JSON format
    # The JsonOutputParser will use the Joke pydantic model to parse the response
    # The prompt includes the format instructions from the output parser to guide the model's response
    # We then create a runnable chain that combines the prompt, the LLM, and the output parser
	output_parser = JsonOutputParser(pydantic_object=Joke)
		input_variables=["query"],
		partial_variables={"format_instructions": format_instructions},
	)

	structured_chain = structured_prompt | llm | output_parser
	structured_result = structured_chain.invoke({"query": joke_query})

	print("\nStructured output:")
	print(structured_result)

def comma_separated_list(llm) -> None:
    # Import the CommaSeparatedListOutputParser to parse LLM responses into Python lists
from langchain.output_parsers import CommaSeparatedListOutputParser

# Create an instance of the parser that will convert comma-separated text into a Python list
output_parser = CommaSeparatedListOutputParser()

# Get formatting instructions that will tell the LLM how to structure its response
# These instructions explain to the LLM that it should return items in a comma-separated format
format_instructions = output_parser.get_format_instructions()

# Create a prompt template that:
# 1. Instructs the LLM to answer the user query
# 2. Includes format instructions so the LLM knows to respond with comma-separated values
# 3. Asks the LLM to list five items of the specified subject
prompt = PromptTemplate(
    template="Answer the user query. {format_instructions}\nList five {subject}.",
    input_variables=["subject"],  # This variable will be provided when the chain is invoked
    partial_variables={"format_instructions": format_instructions},  # This variable is set once when creating the prompt
)

# Build a processing chain that:
# 1. Takes the subject and formats it into the prompt template
# 2. Sends the formatted prompt to the Llama LLM
# 3. Parses the LLM's response into a Python list using the CommaSeparatedListOutputParser

structured_chain = prompt | llm | output_parser



# Invoke the processing chain with "ice cream flavors" as the subject
# This will:
# 1. Substitute "ice cream flavors" into the prompt template
# 2. Send the formatted prompt to the Llama LLM
# 3. Parse the LLM's comma-separated response into a Python list
	structured_result = structured_chain.invoke({"subject": "ice cream flavors"})

	print("\nStructured output:")
	print(structured_result)

def main() -> None:
	setup_runtime(__file__)

	# ---------------------------------------------------------------------
	# 1) PromptTemplate example
	# ---------------------------------------------------------------------
	text_prompt = PromptTemplate.from_template(
		"Tell me one {adjective} joke about {topic}."
	)
	text_input = {"adjective": "funny", "topic": "cats"}
	formatted_text_prompt = text_prompt.invoke(text_input)
	print("PromptTemplate output:")
	print(formatted_text_prompt)

	# ---------------------------------------------------------------------
	# 2) ChatPromptTemplate example
	# ---------------------------------------------------------------------
	chat_prompt = ChatPromptTemplate.from_messages(
		[
			("system", "You are a helpful assistant."),
			("user", "Tell me a joke about {topic}."),
		]
	)
	chat_input = {"topic": "Cats"}
	formatted_chat_prompt = chat_prompt.invoke(chat_input)
	print("\nChatPromptTemplate output:")
	for msg in formatted_chat_prompt.messages:
		print(f"- {msg.type}: {msg.content}")

	# ---------------------------------------------------------------------
	# 3) MessagesPlaceholder example
	# ---------------------------------------------------------------------
	chat_with_placeholder = ChatPromptTemplate.from_messages(
		[
			("system", "You are a helpful assistant."),
			MessagesPlaceholder("msgs"),
		]
	)
	placeholder_input = {
		"msgs": [HumanMessage(content="What is the day after Tuesday?")]
	}
	formatted_placeholder_prompt = chat_with_placeholder.invoke(placeholder_input)
	print("\nMessagesPlaceholder output:")
	for msg in formatted_placeholder_prompt.messages:
		print(f"- {msg.type}: {msg.content}")

	# ---------------------------------------------------------------------
	# 4) Runnable chain example with shared model setup
	# ---------------------------------------------------------------------
	api_key = get_api_key_or_exit()
	chat_models = get_available_chat_models()
	model_primary, _ = select_primary_secondary_models(chat_models)
	llm = build_chat_model(
		model_name=model_primary,
		api_key=api_key,
		temperature=DEFAULT_TEMPERATURE,
		max_tokens=DEFAULT_MAX_TOKENS,
	)

	chain = chat_prompt | llm
	response = chain.invoke(chat_input)
	print("\nLLM response:")
	print(response.content)

	run_structured_output_example(llm)

    comma_separated_list(llm)

if __name__ == "__main__":
	main()