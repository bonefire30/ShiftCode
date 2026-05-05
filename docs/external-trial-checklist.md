# External Trial Checklist

Use this checklist during or immediately after a small external JAVA2GO trial.

## Setup

- Was it clear how to start with the low-cost mock/default path?
- Was it clear that real LLM runs are optional and may cost money?
- Was it clear which API keys or environment variables are needed for a paid run?

## Trial Input

- Was the recommended trial input small enough to understand quickly?
- Did the chosen input feel representative enough for a first evaluation?

## Report Understanding

- Could you distinguish `llmCallStatus` from `conversionStatus`?
- Was it clear why build/test success does not automatically mean full migration success?
- Were `statusReasons` understandable?
- Were `recommendedNextActions` useful?

## Honesty

- Did `partial` and `unsupported` feel honestly reported?
- Did any unsupported behavior feel hidden behind a green success state?
- Did parser/config caveats feel specific enough to act on?

## Cost And Safety

- Did the default path avoid paid LLM API calls?
- Did the guide avoid exposing secrets or suggesting `.env` should be committed?

## Overall Trial Decision

- Would you continue with a deeper trial?
- Which project area looked most promising for automation?
- Which unsupported or partial area blocked trust the most?
