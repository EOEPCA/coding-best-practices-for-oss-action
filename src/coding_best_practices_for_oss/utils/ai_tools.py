import json
from typing import Any

from cachetools import cached
from openai import OpenAI, OpenAIError

from coding_best_practices_for_oss.config import (
    AI_MODEL_NAME,
    AI_MODEL_PROVIDER,
    AI_MODEL_BASE_URL,
    AI_MODEL_API_KEY,
    AI_MODEL_MAX_TOKENS,
    DEFAULT_CHAT_OPTIONS,
    DEFAULT_GENERATE_OPTIONS,
)
from coding_best_practices_for_oss.utils.log_tools import getLogger, dupLogger


logger = getLogger(__name__)
# Apply the same configuration to the openai and http* libraries
dupLogger(__name__, "openai")
dupLogger(__name__, "httpx2")
dupLogger(__name__, "httpcore2")


@cached(cache={})
def query_model(prompt: str, **kwargs: Any) -> dict:
    """
    """
    logger.debug("Querying model '%s' from '%s' ...", AI_MODEL_NAME, AI_MODEL_PROVIDER)
    client = OpenAI(
        api_key = AI_MODEL_API_KEY,
        base_url = AI_MODEL_BASE_URL,
    )

    request_payload: Dict[str, Any] = {
        "model": AI_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": AI_MODEL_MAX_TOKENS,
        "temperature": 0.0,
        #format=json_schema,
        #stream=False,
        #"num_thread": 12,
        #"num_ctx": 65536,  # Set a very high context size limit
        #"num_predict": 1,  # Stop after reading the prompt
        **kwargs,
    }

    seed = 42

    is_gemini = "gemini" in AI_MODEL_NAME.lower() or "googleapis.com" in AI_MODEL_BASE_URL
    if is_gemini:
        # "seed" is not supported by the Google Chat endpoint: 
        # https://ai.google.dev/gemini-api/docs/openai#extra-body
        # request_payload["extra_body"] = {
        #     'extra_body': {
        #         'google': {
        #             'seed': seed
        #         }
        #     }
        # }
        pass
    else:
        # Standard top-level seed for OpenAI models
        request_payload["seed"] = seed
    logger.debug("AI model request payload: %s", request_payload)

    response = client.chat.completions.create(**request_payload)
    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.decoder.JSONDecodeError as ex:
        logger.error("❌ Failed to parse as JSON: %s: %s", text, ex)
        raise ex

@cached(cache={})
def get_models() -> list[str]:
    """IDs of the models offered by the AI model provider ("GET /models"), sorted.

    Returns an empty list if the provider cannot be reached or rejects the request.
    """
    if not AI_MODEL_BASE_URL or not AI_MODEL_API_KEY:
        logger.error("The AI model base URL and API key must be set to list the models")
        return []
    logger.debug("Listing the models of %s (%s) ...", AI_MODEL_PROVIDER, AI_MODEL_BASE_URL)
    client = OpenAI(api_key=AI_MODEL_API_KEY, base_url=AI_MODEL_BASE_URL)
    try:
        return sorted(model.id for model in client.models.list())
    except OpenAIError as err:
        logger.error("Could not get the models from %s (%s): %s", AI_MODEL_NAME, AI_MODEL_BASE_URL, err)
        return []

def get_token_count(system_prompt: str, user_payload: str, json_schema: dict) -> int:
    """
    """
    # payload = {
    #     "model": AI_MODEL_NAME,
    #     "prompt": system_prompt,
    # }
    # response = requests.post(OLLAMA_API_URL + "/tokenize", json=payload)
    # token_count = len(response.json().get("tokens", []))
    # ---
    payload = {
        "model": AI_MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "format": json_schema,
        "stream": False,
        "keep_alive": -1,  # Lock the model in VRAM indefinitely
        "options": {
            # "temperature": 0.0,
            # "seed": 42,
            # "num_thread": 12,
            "num_ctx": 65536,  # Set a very high context size limit
            "num_predict": 1,  # Stop after reading the prompt
        },
    }
    response = requests.post(AI_MODEL_BASE_URL + "/chat", json=payload)
    token_count = response.json().get("prompt_eval_count", 0)
    logger.info("System prompt tokens: %s", token_count)
    return token_count
