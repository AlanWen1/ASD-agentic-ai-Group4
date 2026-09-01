# AI prompts and context management

## Runtime

- Runtime: Ollama
- Approved model: `qwen2.5:0.5b`
- API shape: OpenAI-compatible `POST /v1/chat/completions`
- Temperature: `0.2` for more predictable, data-grounded answers

## System-prompt goals

The implemented system prompt requires the model to:

1. Answer only from the trusted data context supplied by the backend.
2. State when the available income data is insufficient.
3. Never invent amounts, payments, dates, employers, or trends.
4. Avoid investment, tax, legal, credit, or financial-product advice.
5. Explain income patterns and schedules concisely in plain language.

The complete version is stored as `SYSTEM_PROMPT` in `student-3/backend/ai_service.py`.

## Trusted context

Before every AI request, the backend obtains schedules through the Student 3 Database API and calculates:

- expected total;
- received total;
- outstanding expected amount;
- actual-versus-expected variance;
- received, scheduled, late, and cancelled counts;
- active-source count; and
- totals by income source.

The backend then adds the selected month's schedule rows. The model explains these values but does not calculate them.

## Chat-history controls

- The frontend retains the current in-page chat only.
- The backend accepts at most the last six history messages.
- Each history message is limited before it is added to the model context.
- The current user question is limited to 2,000 characters.
- No AI chat data is written to SQLite in Release 0.

## Example prompts for evidence

Use these in the showcase and capture the UI plus terminal request logs:

1. `What is my largest income source this month?`
2. `Which expected payments are still outstanding or late?`
3. `Compare received and expected income and explain the variance.`
4. `When is my next expected payment in the selected month?`

Expected behaviour: the answer uses only visible Student 3 records and refuses unsupported financial advice.
