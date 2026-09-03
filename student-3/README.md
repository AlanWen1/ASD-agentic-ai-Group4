# Student 3 - Income & Pay Schedule Manager

**Owner:** Yongjian Zhou
**Project:** AI-Assisted Personal Money Management System
**Release:** Release 0

## Overview

The Income & Pay Schedule Manager allows authenticated users to manage income
sources, expected payment schedules, and received payments. It calculates
monthly income summaries with Python and SQL, then uses a local Ollama model to
explain the calculated results and answer questions through an AI chat box.

The feature is implemented as three independently containerised microservices:

```text
Frontend (3003)
    -> HTTP
Backend/API (5003)
    -> HTTP
Database API (6003)
    ->
SQLite database
```

The Backend/API never opens the SQLite database directly.

## Main Features

- Complete CRUD operations for income sources
- Complete CRUD operations for pay schedules
- Automatic generation of expected pay dates
- Monthly expected, received, outstanding, and variance calculations
- Filtering by dashboard month
- Shared authentication with bearer-token validation
- Per-user data isolation
- Ollama/Qwen monthly income analysis
- Free-form AI chat grounded in the authenticated user's income data
- Automated Python tests and GitHub Actions CI

## Services and Ports

| Service | Port | Responsibility |
|---|---:|---|
| Student 3 Frontend | 3003 | Web interface and Backend/API proxy |
| Student 3 Backend/API | 5003 | Authentication, business logic, calculations, and AI |
| Student 3 Database API | 6003 | SQLite ownership and CRUD operations |

The integrated application also uses the shared services on ports 3000, 5000,
and 6000.

## Database Tables

### `income_sources`

Stores the source name, income type, standard amount, payment frequency,
active status, and owning user.

### `pay_schedules`

Stores expected and received payment dates, expected and actual amounts,
payment status, notes, linked income source, and owning user.

Both tables include at least ten seeded records for demonstration and testing.

## Authentication and Data Isolation

Users sign in through the shared Finance Application on
`http://localhost:3000`. The shared UI sends the authentication token to the
Student 3 frontend. The frontend stores the token locally, removes it from the
visible URL, and sends it as an `Authorization: Bearer ...` header.

The Backend/API validates the token with the shared access service and passes
only the authenticated user's ID to the Database API. Database queries include
that user ID so one user cannot access another user's income records.

## AI Design

The approved local model is `qwen2.5:0.5b`, served through Ollama.

Python and SQL calculate:

- expected and received totals;
- outstanding income;
- payment counts;
- source totals; and
- actual-versus-expected variance.

The model only explains trusted calculated context. It is instructed not to
invent financial data or provide investment, tax, legal, or financial-product
advice.

## Run the Integrated Application

From the repository root:

```powershell
docker compose up --build -d
```

Open the shared application:

```text
http://localhost:3000
```

After signing in, select **Income & Pay Schedule Manager**.

## Run Student 3 Independently

```powershell
docker compose -f .\docker-compose.student-3.yml up --build -d
```

Open:

```text
http://localhost:3003
```
