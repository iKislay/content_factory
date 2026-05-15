# providers/llm.py
"""
LLM provider — text generation and agentic tool-use loop.

Exports:
    generate(system, user)                        → str
    generate_with_tools(system, user, tools, ...) → (str, list[ToolCall], list[ToolResult])

generate_with_tools() implements the Groq native function-calling protocol.
When Groq is unavailable, an Ollama-compatible simulated tool loop is used as
fallback — same observable behaviour, no native function-calling required.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import config
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from tools.executor import ToolCall, ToolResult
    from tools.registry import ToolDef


class LLMError(Exception):
    """Raised when all LLM providers fail."""
    pass


# ─── Simple text generation (unchanged) ───────────────────────────────────────


@retry(stop=stop_after_attempt(1), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate(system_prompt: str, user_prompt: str) -> str:
    """Generate text using LLM. Tries Groq keys first, then Ollama keys."""
    # 1. Try Groq (Grok) keys
    groq_keys = [k for k in [config.GROQ_API_KEY, config.GROQ_API_KEY2] if k]
    for i, api_key in enumerate(groq_keys):
        try:
            return _groq_generate_with_key(system_prompt, user_prompt, api_key, i+1)
        except Exception as e:
            print(f"[LLM] Groq key {i+1} failed: {e}")
            if i == len(groq_keys) - 1:
                print("[LLM] All Groq keys failed, falling back to Ollama")

    # 2. Try Ollama keys
    ollama_keys = [k for k in [config.OLLAMA_API_KEY1, config.OLLAMA_API_KEY2, config.OLLAMA_API_KEY3] if k]
    if not ollama_keys:
        # If no keys provided, try without key (standard local Ollama)
        return _ollama_generate(system_prompt, user_prompt)
    
    for i, api_key in enumerate(ollama_keys):
        try:
            return _ollama_generate(system_prompt, user_prompt, api_key, i+1)
        except Exception as e:
            print(f"[LLM] Ollama key {i+1} failed: {e}")
            if i == len(ollama_keys) - 1:
                raise LLMError("All LLM providers (Groq and Ollama) failed")
    
    return _ollama_generate(system_prompt, user_prompt)


def _groq_generate_with_key(system_prompt: str, user_prompt: str, api_key: str, key_num: int) -> str:
    """Generate using a specific Groq key."""
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )
    print(f"[LLM] Using groq (key {key_num})")
    return response.choices[0].message.content


def _ollama_generate(system_prompt: str, user_prompt: str, api_key: str = "", key_num: Optional[int] = None) -> str:
    """Generate using Ollama streaming API with optional key."""
    import requests as _requests

    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
        "stream": True,
    }
    
    key_info = f" (key {key_num})" if key_num else ""
    print(f"[LLM] Trying ollama{key_info}...")
    
    response = _requests.post(url, json=payload, headers=headers, timeout=120)
    if response.status_code != 200:
        raise LLMError(f"Ollama returned status {response.status_code}")

    full_text = ""
    for line in response.iter_lines():
        if line:
            data = line.decode("utf-8")
            if data.startswith("{"):
                chunk = json.loads(data)
                if "response" in chunk:
                    full_text += chunk["response"]

    return full_text.strip()


# ─── Agentic tool-use loop ─────────────────────────────────────────────────────


def generate_with_tools(
    system_prompt: str,
    user_prompt: str,
    tools: List["ToolDef"],
    executor: Any,  # ToolExecutor — avoid circular import at module level
    max_rounds: int = 3,
) -> Tuple[str, List["ToolCall"], List["ToolResult"]]:
    """
    Run an agentic LLM loop where the model can invoke tools autonomously.
    """
    if not tools:
        # No tools — just use regular generate()
        text = generate(system_prompt, user_prompt)
        return text, [], []

    # Try Groq tool loop if available
    groq_keys = [k for k in [config.GROQ_API_KEY, config.GROQ_API_KEY2] if k]
    if config.LLM_PROVIDER == "groq" and groq_keys:
        try:
            return _groq_tool_loop(
                system_prompt, user_prompt, tools, executor, max_rounds
            )
        except Exception as e:
            print(f"[LLM] Groq tool loop failed: {e}, falling back to Ollama tool loop")

    # Fallback to Ollama tool loop
    return _ollama_tool_loop(
        system_prompt, user_prompt, tools, executor, max_rounds
    )


# ─── Groq native function-calling loop ────────────────────────────────────────


def _groq_tool_loop(
    system_prompt: str,
    user_prompt: str,
    tools: List["ToolDef"],
    executor: Any,
    max_rounds: int,
) -> Tuple[str, List, List]:
    """Groq API native function-calling loop with fallback."""
    from tools.executor import ToolCall  # local import avoids circular dep

    keys = [k for k in [config.GROQ_API_KEY, config.GROQ_API_KEY2] if k]
    if not keys:
        raise LLMError("GROQ_API_KEY not set")
    
    groq_tools = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
        if t is not None
    ]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    
    last_error = None
    for key_idx, api_key in enumerate(keys):
        try:
            client = Groq(api_key=api_key)
            break
        except Exception as e:
            last_error = e
            if key_idx < len(keys) - 1:
                print(f"[LLM] Groq key {key_idx+1} init failed, trying fallback...")
                continue
            raise LLMError(f"All Groq keys failed: {last_error}")

    groq_tools = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
        if t is not None
    ]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    all_calls: List = []
    all_results: List = []
    last_content = ""

    for round_num in range(max_rounds + 1):
        print(f"[LLM] groq tool-loop round {round_num + 1}/{max_rounds + 1}")

        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=2000,
        )

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        msg = choice.message
        last_content = msg.content or ""

        if finish_reason == "tool_calls" and msg.tool_calls:
            # Append assistant's tool-call message
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each call and append tool-role messages
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                call = ToolCall(
                    tool_name=tc.function.name,
                    arguments=args,
                    call_id=tc.id,
                )
                all_calls.append(call)

                result = executor.execute(call)
                all_results.append(result)

                print(
                    f"[LLM]   tool={call.tool_name} "
                    f"ok={result.is_ok()} "
                    f"({result.duration_ms:.0f}ms)"
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.to_llm_content(),
                })
        else:
            # finish_reason == "stop" — final answer
            break

    return last_content, all_calls, all_results


# ─── Ollama simulated tool loop ────────────────────────────────────────────────


def _ollama_tool_loop(
    system_prompt: str,
    user_prompt: str,
    tools: List["ToolDef"],
    executor: Any,
    max_rounds: int,
) -> Tuple[str, List, List]:
    """
    Simulated tool loop for Ollama (no native function-calling support).
    
    Uses the robust generate() function for each step to benefit from
    the 5-key fallback logic.
    """
    from tools.executor import ToolCall

    tool_descriptions = "\n".join(
        f"  • {t.name}: {t.description}" for t in tools if t is not None
    )
    augmented_system = (
        f"{system_prompt}\n\n"
        f"You have access to the following tools:\n{tool_descriptions}\n\n"
        f"To call a tool, respond with ONLY this JSON (nothing else):\n"
        f'{{"tool_call": {{"name": "<tool_name>", "arguments": {{...}}}}}}\n\n'
        f"When you have your final answer and no more tools are needed, "
        f"respond normally with text."
    )

    conversation = user_prompt
    all_calls: List = []
    all_results: List = []
    last_text = ""

    for round_num in range(max_rounds + 1):
        # Use generate() to get 5-key fallback benefit
        response = generate(augmented_system, conversation)
        last_text = response

        # Try to parse as tool call
        tc_data = _parse_ollama_tool_call(response)

        if tc_data and round_num < max_rounds:
            call = ToolCall(
                tool_name=tc_data["name"],
                arguments=tc_data.get("arguments", {}),
                call_id=f"ollama_{round_num}",
            )
            all_calls.append(call)

            result = executor.execute(call)
            all_results.append(result)

            print(
                f"[LLM/ollama] tool={call.tool_name} "
                f"ok={result.is_ok()} ({result.duration_ms:.0f}ms)"
            )

            # Inject result into conversation
            conversation = (
                f"{conversation}\n\n"
                f"Tool '{call.tool_name}' result:\n"
                f"{result.to_llm_content()}\n\n"
                f"Continue with your task:"
            )
        else:
            # No tool call — this is the final answer
            break

    return last_text, all_calls, all_results


def _parse_ollama_tool_call(text: str) -> Optional[dict]:
    """Extract tool_call dict from Ollama response, or None if not a tool call."""
    text = text.strip()

    # Remove markdown fences if present
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

    if not text.startswith("{"):
        return None

    try:
        data = json.loads(text)
        if "tool_call" in data:
            tc = data["tool_call"]
            if isinstance(tc, dict) and "name" in tc:
                return tc
    except (json.JSONDecodeError, KeyError):
        pass

    return None