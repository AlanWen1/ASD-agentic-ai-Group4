# Finance Application service

This is the main finance portal at port 3000.

It provides registration/login, a home page for services, and bill CRUD. It has no AI chat. Bill CRUD is forwarded through the Bill Tracker database API; the finance backend never opens the bill SQLite file.

The finance database service at port 6000 stores users and session tokens in SQLite behind its HTTP API.
