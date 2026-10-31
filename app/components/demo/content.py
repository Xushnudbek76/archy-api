SAMPLES = (
    {
        "key": "transactions",
        "title": "Database transactions",
        "course": "Database systems",
        "text": (
            "A transaction groups database operations into one unit. "
            "Atomicity means every operation succeeds or the transaction rolls back. "
            "Consistency preserves database constraints. Isolation controls how concurrent "
            "transactions interact. Durability preserves committed changes after a restart. "
            "A bank transfer must debit one account and credit another in the same transaction."
        ),
        "overview": "Transactions keep related changes together and protect database consistency.",
        "questions": (
            (
                "What does atomicity guarantee?",
                [
                    "All operations succeed or roll back",
                    "Faster reads",
                    "No indexes",
                    "Unlimited connections",
                ],
                0,
            ),
            (
                "Which property preserves committed changes?",
                ["Isolation", "Durability", "Compression", "Pagination"],
                1,
            ),
            ("A bank transfer should use one transaction.", ["True", "False"], 0),
            (
                "What does isolation control?",
                ["Disk capacity", "Password length", "Concurrent transactions", "HTTP headers"],
                2,
            ),
            ("Consistency preserves database constraints.", ["True", "False"], 0),
        ),
        "question": "Why should a bank transfer use one transaction?",
        "answer": (
            "The debit and credit must succeed together. If either fails, atomicity rolls back "
            "the entire transfer so money cannot disappear between the two operations."
        ),
    },
    {
        "key": "http",
        "title": "HTTP request essentials",
        "course": "Web development",
        "text": (
            "HTTP uses requests and responses. GET reads a resource without changing it. "
            "POST submits data and may create a resource. A 200 response indicates success; "
            "404 means the resource was not found and 429 means the client should slow down. "
            "HTTPS encrypts traffic in transit. Cookies can maintain a session between requests. "
            "An HttpOnly cookie cannot be read by browser JavaScript."
        ),
        "overview": "HTTP methods describe the request; status codes describe the result.",
        "questions": (
            ("Which method reads a resource?", ["POST", "GET", "PATCH", "DELETE"], 1),
            ("What does status 404 mean?", ["Success", "Slow down", "Not found", "Created"], 2),
            ("HTTPS encrypts traffic in transit.", ["True", "False"], 0),
            (
                "What does status 429 ask the client to do?",
                ["Slow down", "Delete cookies", "Change language", "Upload a PDF"],
                0,
            ),
            ("JavaScript can read an HttpOnly cookie.", ["True", "False"], 1),
        ),
        "question": "Why use an HttpOnly cookie for a session?",
        "answer": (
            "HttpOnly prevents browser JavaScript from reading the cookie. The browser can still "
            "send it with appropriate requests, allowing the server to identify the session."
        ),
    },
)
