# Architecture

## Database Architecture
Use a database abstraction layer.

Conceptually:

SequenceDatabase
├── NCBI client
├── ENA client
└── future database clients

Database-specific API code must not be tightly coupled to the analysis layer.

## Analysis Architecture
Keep analysis functionality modular, for example:

analysis/
├── composition
├── statistics
├── similarity
├── alignment
└── quality_control

## Explicitly Out of Scope
Do not introduce, unless explicitly requested:
- Kubernetes
- microservices
- authentication
- cloud infrastructure
- distributed systems
- unnecessary databases
- unnecessary background workers
