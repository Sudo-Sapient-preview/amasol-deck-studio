"""Claude through the LLM proxy (Anthropic Messages API) and the tool-use loop each pipeline stage runs."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

import anthropic

from . import config
from .tools import TOOLS, ToolError

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Caching: the system prompt carries one 1h breakpoint (prompts.system_prompt). The proxy adds its own breakpoints
# on the conversation, so a top-level cache_control here would exceed the API's limit of 4.


class Cancelled(Exception):
    pass


class StageFailed(Exception):
    pass


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    calls: int = 0

    def add(self, u):
        self.input += u.input_tokens or 0
        self.output += u.output_tokens or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.calls += 1

    def as_dict(self):
        return {"input": self.input, "output": self.output, "cache_read": self.cache_read,
                "cache_write": self.cache_write, "calls": self.calls}


def make_client() -> anthropic.Anthropic:
    if not config.LLM_API_KEY:
        raise RuntimeError("No LLM proxy key: set LLM_PROXY_API_KEY")
    return anthropic.Anthropic(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY, max_retries=4,
                               timeout=anthropic.Timeout(900.0, connect=20.0))


@dataclass
class Agent:
    client: anthropic.Anthropic
    model: str
    system: list[dict]
    usage: Usage
    log: Callable[..., None]
    cancelled: Callable[[], bool]
    effort: str = "high"
    tools: list[dict] = field(default_factory=lambda: TOOLS)

    def _call(self, messages: list[dict]):
        last_err = None
        for attempt in range(3):
            if self.cancelled():
                raise Cancelled()
            try:
                with self.client.beta.messages.stream(
                    model=self.model,
                    max_tokens=64000,
                    system=self.system,
                    tools=self.tools,
                    messages=messages,
                    thinking={"type": "adaptive"},
                    output_config={"effort": self.effort},
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                ) as stream:
                    msg = stream.get_final_message()
                self.usage.add(msg.usage)
                return msg
            except (anthropic.BadRequestError, anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                    anthropic.NotFoundError):
                raise
            except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                last_err = e
                self.log("note", f"Model call failed ({type(e).__name__}), retrying")
                time.sleep(8 * (attempt + 1))
        raise StageFailed(f"The model could not be reached: {last_err}")

    def run(self, stage: str, first_user: list[dict] | str, handle: Callable[[str, dict], object],
            max_turns: int = 40) -> str:
        """Loop until handle() accepts finish_stage (returns ('finished', summary))."""
        messages: list[dict] = [{"role": "user", "content": first_user}]
        nudges = 0
        for turn in range(max_turns):
            if self.cancelled():
                raise Cancelled()
            msg = self._call(messages)
            messages.append({"role": "assistant", "content": msg.content})
            if msg.stop_reason == "refusal":
                raise StageFailed("The model declined this request (safety refusal). Rephrase the input and retry.")
            for b in msg.content:
                if b.type == "text" and b.text.strip():
                    self.log("agent", b.text.strip())
            uses = [b for b in msg.content if b.type == "tool_use"]
            if msg.stop_reason == "max_tokens":
                if uses:
                    messages.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": u.id, "is_error": True,
                         "content": "Your output hit the length limit and this call was cut off. Write in smaller "
                                    "pieces (edit_file instead of rewriting whole files)."} for u in uses]})
                else:
                    messages.append({"role": "user", "content": "Your reply was cut off. Continue with tool calls."})
                continue
            if not uses:
                nudges += 1
                if nudges > 3:
                    raise StageFailed(f"{stage}: the model stopped without finishing the stage")
                messages.append({"role": "user", "content":
                                 "Continue the stage with tool calls. When the goal is met, call finish_stage."})
                continue
            results, finished = [], None
            for u in uses:
                if self.cancelled():
                    raise Cancelled()
                try:
                    inp = u.input if isinstance(u.input, dict) else json.loads(u.input or "{}")
                    out = handle(u.name, inp)
                    if isinstance(out, tuple) and out and out[0] == "finished":
                        finished = out[1]
                        content = "Stage accepted."
                    else:
                        content = out
                    results.append({"type": "tool_result", "tool_use_id": u.id, "content": content})
                except ToolError as e:
                    results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True, "content": str(e)})
                except (Cancelled, StageFailed):
                    raise
                except Exception as e:  # noqa: BLE001 - tool crash goes back to the model, not to the user
                    results.append({"type": "tool_result", "tool_use_id": u.id, "is_error": True,
                                    "content": f"tool crashed: {type(e).__name__}: {e}"})
            if finished is not None:
                return finished
            messages.append({"role": "user", "content": results})
        raise StageFailed(f"{stage}: not finished after {max_turns} model turns")
