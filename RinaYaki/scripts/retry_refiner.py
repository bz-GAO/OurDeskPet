"""Retry one refiner against an existing smoke-test draft without rerunning MT."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from rinayaki.translation import DashScopeOpenAIClient, refinement_payload


CANDIDATES = {
    "deepseek": ("deepseek-v4.1-flash", "low"),
    "glm": ("ZHIPU/GLM-5.3-Flash", "low"),
    "qwen": ("qwen3.8-flash", "none"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", choices=sorted(CANDIDATES))
    parser.add_argument("--from-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    previous = json.loads(args.from_results.read_text(encoding="utf-8"))
    source = previous["source_text"]
    draft = previous["translation"]["result"]["content"]
    model, effort = CANDIDATES[args.candidate]
    payload = refinement_payload(source, draft, model=model, reasoning_effort=effort)

    project_root = Path(__file__).resolve().parents[1]
    client = DashScopeOpenAIClient.from_environment(dotenv_path=project_root / ".env")
    result = client.chat_completions(payload)
    record = {
        "candidate": args.candidate,
        "base_url": client.base_url,
        "request": payload,
        "result": asdict(result),
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
