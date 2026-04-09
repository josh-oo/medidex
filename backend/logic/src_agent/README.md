# AI Demo Server

Minimal FastAPI + LangGraph demo that evaluates a report against a list of studies.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```


Then run from the repo root:

```bash
uvicorn backend.main:app --reload --port 8001
```

## Example

```bash
curl "http://localhost:8001/evaluate/mock"
```

For a real request, POST `/evaluate` using the `ReportDto` and `StudyDto` shapes. See the mock objects in `backend/mock_data.py`.

## Module Map

- `backend/main.py`: FastAPI entrypoint and routes.
- `backend/schemas.py`: Pydantic DTOs and `EvalState`.
- `backend/prompts.py`: Default LLM prompt templates.
- `backend/llm.py`: LLM client initialization (loads env via config import).
- `backend/llm_payloads.py`: JSON payload builders for LLM calls.
- Structured outputs are enforced via LangChain `with_structured_output` in the graph; no standalone parsers.
- `backend/evaluation_utils.py`: Bucket + lookup helpers.
- `backend/evaluation_graph.py`: LangGraph workflow nodes + graph construction.
- `backend/evaluator.py`: Evaluation orchestrator (builds state + runs graph).
- `backend/streaming.py`: SSE stream event summarizer.
- `backend/mock_data.py`: Mock report/studies used by mock endpoints.
