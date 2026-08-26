---
name: database-integration
description: Implement or review code that talks to NCBI (Entrez/E-utilities) or ENA APIs for retrieving nucleotide sequences and metadata. Use when writing or editing code under a database/ or clients/ directory, or when the user mentions NCBI, Entrez, ENA, accession numbers, rate limits, retries, or fetching sequences from a public database.
---

# Database Integration (NCBI / ENA)

Guidance for building reliable clients against external nucleotide sequence databases.

## Core Rules
- Treat every external API call as something that WILL eventually fail: timeout, 429, 500, malformed XML/JSON, or a record that doesn't exist. Code must handle all of these explicitly, not just the happy path.
- Never hard-code a fake/sample API response into production code. Use mocks/fixtures only inside `tests/`.
- Keep each database client (NCBI client, ENA client) behind the same abstract interface (e.g. a `SequenceDatabase` protocol/ABC) so the analysis layer never imports `requests`/`Bio.Entrez` directly.

## NCBI (Entrez / E-utilities)
- Always set `Entrez.email` (and `Entrez.api_key` if available) before making requests - NCBI requires this and may block requests without it.
- Rate limits: 3 requests/second without an API key, 10 requests/second with one. Implement client-side throttling (e.g. a token bucket or simple `time.sleep`) rather than relying on NCBI to reject you gracefully.
- Use `Bio.Entrez.efetch` with `rettype="fasta"` or `rettype="gb"` and `retmode="text"` for sequence retrieval; always wrap the returned handle in a `try/finally` (or context manager) to ensure it's closed.
- Validate the accession format before calling the API (basic regex sanity check) to fail fast on obviously malformed input, but do not assume a well-formatted accession exists - the API call can still return "not found."

## ENA (European Nucleotide Archive)
- ENA's REST API returns plain FASTA/text for sequence endpoints and JSON for the search/metadata endpoints - do not assume both endpoints return the same format.
- Check HTTP status code explicitly; a 200 with an empty body can still mean "no data," which is different from a 404.

## Retries & Timeouts
- Set an explicit connect and read timeout on every HTTP call - never leave it unbounded.
- Use exponential backoff with jitter for retries on transient errors (timeouts, 5xx, connection errors). Do NOT retry on 4xx errors other than 429 (rate limit) - a 400/404 will not succeed on retry.
- Cap total retry attempts (e.g. 3-5) and surface a clear typed exception (e.g. `SequenceNotFoundError`, `DatabaseUnavailableError`) after retries are exhausted - never let a raw `requests.exceptions.*` leak into the analysis layer.

## Accession Handling & Metadata Normalization
- Never assume an accession exists just because it's well-formed. The client must handle "not found" as a distinct, expected outcome (not an exception that crashes the request), typically returning `None` or raising a specific `SequenceNotFoundError` that calling code is expected to catch.
- Never assume optional metadata fields (organism, collection date, strain, etc.) are present in the response - access them defensively and represent missing fields as `None`/absent, not empty string or fabricated placeholder text.
- When normalizing metadata across NCBI and ENA (which use different field names/structures), keep the raw provider response available alongside the normalized result where practical, so provenance isn't lost.

## Testing
- Use `pytest` fixtures with recorded/mocked HTTP responses (e.g. `responses` library or saved fixture files) - never hit the real NCBI/ENA API in automated tests.
- Test explicitly for: timeout, HTTP 429, HTTP 500, malformed response body, accession not found, and missing optional metadata fields.
