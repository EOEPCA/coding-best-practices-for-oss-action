import json
import logging
from typing import Any

from cachetools import cached
from openai import OpenAI

from coding_best_practices_for_oss.config import (
    AI_MODEL_NAME,
    AI_MODEL_PROVIDER,
    AI_MODEL_BASE_URL,
    AI_MODEL_API_KEY,
    AI_MODEL_MAX_TOKENS,
    DEFAULT_CHAT_OPTIONS,
    DEFAULT_GENERATE_OPTIONS,
)


logger = logging.getLogger(__name__)

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
def get_models():
    """
    """
    try:
        response = requests.get(
            OPENAI_URL + "/models",
            headers = {
                "Authorization": "Bearer " + OPENAI_KEY,
                "Content-Type": "application/json",
            }
        )
        response.raise_for_status()
        models_data = response.json().get("data", [])
        model_names = [model["id"] for model in models_data]
        return model_names
    except requests.exceptions.RequestException as err:
        logger.error("Could not connect to the model engine API: %s", err)
        return []

def get_token_count(system_prompt: str, user_payload: str, json_schema: dict) -> int:
    """
    """
    # payload = {
    #     "model": OLLAMA_MODEL,
    #     "prompt": system_prompt,
    # }
    # response = requests.post(OLLAMA_API_URL + "/tokenize", json=payload)
    # token_count = len(response.json().get("tokens", []))
    # ---
    payload = {
        "model": OLLAMA_MODEL,
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
    response = requests.post(OLLAMA_API_URL + "/chat", json=payload)
    token_count = response.json().get("prompt_eval_count", 0)
    logger.info("System prompt tokens: %s", token_count)
    return token_count
