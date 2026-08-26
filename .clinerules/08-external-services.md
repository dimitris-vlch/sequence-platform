# Data and External Services

- Treat external database APIs as unreliable external dependencies.
- Handle HTTP errors, timeouts, malformed responses, rate limits, and missing records gracefully.
- Never assume that an accession exists.
- Never assume metadata fields are present.
- Do not hard-code fake database responses into production code.
- Use mocks/fixtures for tests when appropriate.
