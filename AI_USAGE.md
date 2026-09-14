# AI Usage

## Tools Used

* ChatGPT/Codex for architecture planning, scaffolding, implementation, and documentation.
* Local shell commands for repository inspection and validation.

## Where AI Accelerated Delivery

* Produced README, architecture, and operational notes aligned with the challenge rubric.
* Helped keep frontend, backend, Docker, and CI artifacts consistent.

## Where AI Suggestions Were Rejected or Adjusted

* Avoided floating-point balance storage and used integer minor units plus Decimal conversion.
* Avoided synchronous exchange-provider calls inside transfers; persisted rates are used for traceability and resilience.
* Kept the frontend focused on core wallet workflows instead of a marketing-style landing page.
* Chose a simpler startup table-creation path for the challenge while documenting that production should use Alembic migrations.

