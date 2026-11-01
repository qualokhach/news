# AppNho News — AI provider order and cost guardrails

Provider order is Gemini → Grok/xAI → OpenRouter.

- Gemini: the pipeline intersects the authenticated `models.list` response with stable, free-tier text models. Current priority is `gemini-3.5-flash-lite`, followed by the still-listed `gemini-3.1-flash-lite` and `gemini-2.5-flash-lite`. A model is used only when the API reports `generateContent`.
- Grok: the pipeline discovers current text models from the authenticated xAI language-model catalog, with `/v1/models` as fallback. It never guesses a retired slug. It prefers `grok-4.7` if returned; otherwise it chooses the lowest-priced eligible Grok text model returned by the account. Default cost ceilings are USD 5/M input and USD 20/M output, configurable with `XAI_MAX_INPUT_USD_PER_MILLION` and `XAI_MAX_OUTPUT_USD_PER_MILLION`.
- OpenRouter: only models ending in `:free` with both prompt and completion prices equal to zero are eligible. An explicit `OPENROUTER_MODEL` cannot bypass this check.

Grok generation uses xAI’s primary `/v1/responses` endpoint with `store=false`; the pipeline does not use the legacy Chat Completions endpoint. Grok is a paid fallback. A research run can use up to 3 Grok calls by default (`MAX_GROK_CALLS_PER_RUN`). OpenRouter free-model calls are capped at 8 per run (`MAX_OPENROUTER_CALLS_PER_RUN`) and model catalogs are cached for the duration of a run. The pipeline records provider/model selection in the run log. It does not promise zero-cost operation when Grok is reached. The API preflight validates credentials and live model availability; actual generation is tested by the research run itself.
