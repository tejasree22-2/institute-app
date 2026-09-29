"""Create tables and seed sample data so the app has something to demo.

Run from the institute-app/ directory:
    python3 scripts/init_db.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)

from app.config import settings  # noqa: E402
from app.database import Base, engine, SessionLocal, ensure_columns  # noqa: E402
from app import models  # noqa: E402
from app.auth import hash_password  # noqa: E402

if settings.is_production:
    sys.exit("init_db.py wipes the database and seeds demo accounts — refusing to run with APP_ENV=production. "
             "Use scripts/create_instructor.py to create the first real account.")

if not settings.database_url.startswith("sqlite") and "--force" not in sys.argv:
    sys.exit("DATABASE_URL points at a server database — init_db.py would wipe it. Re-run with --force if you mean it.")

# wipe any existing demo DB so this script is idempotent
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
ensure_columns()
db = SessionLocal()

now = datetime.now(timezone.utc)


def days_ago(n):
    return now - timedelta(days=n)


# ---------------------------------------------------------------- users ----
instructor = models.User(
    name="Anita Sharma", email="anita@institute.edu",
    password_hash=hash_password("instructor123"), role="instructor",
    created_at=days_ago(60),
)
db.add(instructor)
db.flush()

students_data = [
    ("Ravi Kumar", "ravi@institute.edu"),
    ("Priya Singh", "priya@institute.edu"),
    ("Aman Gupta", "aman@institute.edu"),
    ("Sneha Patel", "sneha@institute.edu"),
    ("Karthik Rao", "karthik@institute.edu"),
]
students = {}
for name, email in students_data:
    u = models.User(
        name=name, email=email, password_hash=hash_password("student123"),
        role="student", created_at=days_ago(45),
    )
    db.add(u)
    db.flush()
    students[name] = u

# -------------------------------------------------------------- batches ----
batch_morning = models.Batch(name="Python Basics - Morning", created_by=instructor.id, created_at=days_ago(40))
batch_evening = models.Batch(name="Python Basics - Evening", created_by=instructor.id, created_at=days_ago(35))
db.add_all([batch_morning, batch_evening])
db.flush()

for name in ("Ravi Kumar", "Priya Singh", "Aman Gupta"):
    db.add(models.BatchStudent(batch_id=batch_morning.id, student_id=students[name].id))
for name in ("Sneha Patel", "Karthik Rao"):
    db.add(models.BatchStudent(batch_id=batch_evening.id, student_id=students[name].id))
db.flush()

# ------------------------------------------------------------- questions ----
def make_question(title, difficulty, description, starter_code, reference_solution, test_cases, created_days_ago, verified=True):
    q = models.CodingQuestion(
        title=title, difficulty=difficulty, description=description,
        starter_code=starter_code, reference_solution=reference_solution,
        language="python", created_by=instructor.id,
        created_at=days_ago(created_days_ago), updated_at=days_ago(created_days_ago),
    )
    db.add(q)
    db.flush()
    for i, (stdin, expected, hidden) in enumerate(test_cases):
        db.add(models.TestCase(
            question_id=q.id, stdin=stdin, expected_stdout=expected,
            is_hidden=hidden, ordering=i,
        ))
    db.flush()
    if verified:
        q.verified_at = days_ago(created_days_ago - 1) if created_days_ago > 0 else now
    return q


q1 = make_question(
    title="Sum of Two Numbers",
    difficulty="easy",
    description=(
        "## Sum of Two Numbers\n\n"
        "Read two integers `a` and `b` from standard input (space-separated on one line) "
        "and print their sum.\n\n"
        "**Sample Input**\n```\n3 5\n```\n**Sample Output**\n```\n8\n```"
    ),
    starter_code="a, b = map(int, input().split())\n# write your code here\n",
    reference_solution="a, b = map(int, input().split())\nprint(a + b)\n",
    test_cases=[
        ("3 5", "8", False),
        ("10 20", "30", False),
        ("-4 4", "0", True),
        ("100 250", "350", True),
    ],
    created_days_ago=30,
)

q2 = make_question(
    title="Reverse a String",
    difficulty="easy",
    description=(
        "## Reverse a String\n\n"
        "Read a single line of text and print it reversed.\n\n"
        "**Sample Input**\n```\nhello\n```\n**Sample Output**\n```\nolleh\n```"
    ),
    starter_code="s = input()\n# write your code here\n",
    reference_solution="s = input()\nprint(s[::-1])\n",
    test_cases=[
        ("hello", "olleh", False),
        ("python", "nohtyp", False),
        ("a", "a", True),
        ("racecar", "racecar", True),
    ],
    created_days_ago=28,
)

q3 = make_question(
    title="Find Maximum in a List",
    difficulty="medium",
    description=(
        "## Find Maximum in a List\n\n"
        "The first line has an integer `n`. The second line has `n` space-separated integers. "
        "Print the maximum value.\n\n"
        "**Sample Input**\n```\n5\n3 7 2 9 4\n```\n**Sample Output**\n```\n9\n```"
    ),
    starter_code="n = int(input())\nnums = list(map(int, input().split()))\n# write your code here\n",
    reference_solution="n = int(input())\nnums = list(map(int, input().split()))\nprint(max(nums))\n",
    test_cases=[
        ("5\n3 7 2 9 4", "9", False),
        ("3\n-1 -5 -2", "-1", False),
        ("1\n42", "42", True),
        ("6\n10 20 30 5 30 1", "30", True),
    ],
    created_days_ago=21,
)

q4 = make_question(
    title="Check Prime Number",
    difficulty="medium",
    description=(
        "## Check Prime Number\n\n"
        "Read an integer `n`. Print `Yes` if it is prime, otherwise print `No`.\n\n"
        "**Sample Input**\n```\n7\n```\n**Sample Output**\n```\nYes\n```"
    ),
    starter_code="n = int(input())\n# write your code here\n",
    reference_solution=(
        "n = int(input())\n"
        "if n < 2:\n"
        "    print('No')\n"
        "else:\n"
        "    is_prime = True\n"
        "    i = 2\n"
        "    while i * i <= n:\n"
        "        if n % i == 0:\n"
        "            is_prime = False\n"
        "            break\n"
        "        i += 1\n"
        "    print('Yes' if is_prime else 'No')\n"
    ),
    test_cases=[
        ("7", "Yes", False),
        ("10", "No", False),
        ("1", "No", True),
        ("97", "Yes", True),
    ],
    created_days_ago=14,
)

q5 = make_question(
    title="Fibonacci Series",
    difficulty="hard",
    description=(
        "## Fibonacci Series\n\n"
        "Read an integer `n`. Print the first `n` Fibonacci numbers (starting 0, 1), "
        "space-separated on one line.\n\n"
        "**Sample Input**\n```\n5\n```\n**Sample Output**\n```\n0 1 1 2 3\n```"
    ),
    starter_code="n = int(input())\n# write your code here\n",
    reference_solution=(
        "n = int(input())\n"
        "seq = []\n"
        "a, b = 0, 1\n"
        "for _ in range(n):\n"
        "    seq.append(a)\n"
        "    a, b = b, a + b\n"
        "print(' '.join(map(str, seq)))\n"
    ),
    test_cases=[
        ("5", "0 1 1 2 3", False),
        ("1", "0", False),
        ("2", "0 1", True),
        ("8", "0 1 1 2 3 5 8 13", True),
    ],
    created_days_ago=7,
)

# an unverified question still in progress, to show the Library's "needs verify" state
q6 = models.CodingQuestion(
    title="Palindrome Check",
    difficulty="easy",
    description=(
        "## Palindrome Check\n\nRead a string and print `Yes` if it reads the same "
        "forwards and backwards, else `No`."
    ),
    starter_code="s = input()\n# write your code here\n",
    reference_solution="s = input()\nprint('Yes' if s == s[::-1] else 'No')\n",
    language="python",
    created_by=instructor.id,
    created_at=days_ago(2), updated_at=days_ago(2),
)
db.add(q6)
db.flush()
db.add(models.TestCase(question_id=q6.id, stdin="madam", expected_stdout="Yes", is_hidden=False, ordering=0))
db.add(models.TestCase(question_id=q6.id, stdin="hello", expected_stdout="No", is_hidden=False, ordering=1))
db.flush()

db.commit()

# ----------------------------------------------------------- assignments ----
def assign(question, batch, assigned_days_ago):
    db.add(models.Assignment(question_id=question.id, batch_id=batch.id, assigned_at=days_ago(assigned_days_ago)))

assign(q1, batch_morning, 29)
assign(q2, batch_morning, 27)
assign(q3, batch_morning, 20)
assign(q4, batch_morning, 13)
assign(q1, batch_evening, 29)
assign(q2, batch_evening, 27)
assign(q5, batch_evening, 6)
db.commit()

# ---------------------------------------------------------- submissions ----
def submit(student_name, question, code, passed, total, submitted_days_ago, test_cases_ordered):
    status = "all_passed" if passed == total else ("failed" if passed == 0 else "partial")
    sub = models.Submission(
        student_id=students[student_name].id, question_id=question.id, code=code,
        status=status, passed_count=passed, total_count=total,
        submitted_at=days_ago(submitted_days_ago),
    )
    db.add(sub)
    db.flush()
    for i, tc in enumerate(test_cases_ordered):
        db.add(models.SubmissionResult(
            submission_id=sub.id, test_case_id=tc.id,
            passed=(i < passed), actual_output="", runtime_ms=20 + i * 5,
        ))
    db.flush()
    return sub


q1_tcs = q1.test_cases
q2_tcs = q2.test_cases
q3_tcs = q3.test_cases
q4_tcs = q4.test_cases
q5_tcs = q5.test_cases

# Ravi: strong performer, all passed on everything attempted
submit("Ravi Kumar", q1, "a, b = map(int, input().split())\nprint(a + b)\n", 4, 4, 28, q1_tcs)
submit("Ravi Kumar", q2, "s = input()\nprint(s[::-1])\n", 4, 4, 26, q2_tcs)
submit("Ravi Kumar", q3, "n = int(input())\nnums = list(map(int, input().split()))\nprint(max(nums))\n", 4, 4, 19, q3_tcs)

# Priya: partially passing, a couple of attempts
submit("Priya Singh", q1, "a, b = map(int, input().split())\nprint(a + b)\n", 4, 4, 27, q1_tcs)
submit("Priya Singh", q2, "s = input()\nprint(s)\n", 2, 4, 25, q2_tcs)
submit("Priya Singh", q2, "s = input()\nprint(s[::-1])\n", 4, 4, 24, q2_tcs)
submit("Priya Singh", q3, "n = int(input())\nnums = list(map(int, input().split()))\nprint(min(nums))\n", 1, 4, 18, q3_tcs)

# Aman: only attempted question 1, partial
submit("Aman Gupta", q1, "a, b = map(int, input().split())\nprint(a - b)\n", 1, 4, 26, q1_tcs)
submit("Aman Gupta", q1, "a, b = map(int, input().split())\nprint(a + b)\n", 4, 4, 25, q1_tcs)
# q4 assigned to Aman's batch but not attempted -> not_started

# Sneha (evening batch): all passed on q1, partial on q5
submit("Sneha Patel", q1, "a, b = map(int, input().split())\nprint(a + b)\n", 4, 4, 25, q1_tcs)
submit("Sneha Patel", q2, "s = input()\nprint(s[::-1])\n", 4, 4, 23, q2_tcs)
submit("Sneha Patel", q5, "n = int(input())\nprint(' '.join(['0'] * n))\n", 1, 4, 5, q5_tcs)

# Karthik (evening batch): not attempted anything -> all not_started

db.commit()

# --------------------------------------------------------------- notes ----
db.add(models.Note(
    student_id=students["Ravi Kumar"].id, question_id=q1.id,
    content="Straightforward — map(int, input().split()) trick is handy for reading two ints on one line.",
    updated_at=days_ago(28),
))
db.add(models.Note(
    student_id=students["Priya Singh"].id, question_id=q2.id,
    content="Forgot slicing syntax at first ([::-1]) — reversed a string wrong on first try. Need to review slice notation.",
    updated_at=days_ago(24),
))
db.add(models.Note(
    student_id=students["Sneha Patel"].id, question_id=q5.id,
    content="Need to revisit how Fibonacci sequences are generated iteratively — my first attempt just printed zeros.",
    updated_at=days_ago(5),
))
db.commit()

print("Seed complete.")
print(f"  Database: {engine.url.render_as_string(hide_password=True)}")
print("  Instructor login: anita@institute.edu / instructor123")
print("  Student logins:   ravi@institute.edu / student123  (Python Basics - Morning)")
print("                    priya@institute.edu / student123 (Python Basics - Morning)")
print("                    aman@institute.edu / student123  (Python Basics - Morning)")
print("                    sneha@institute.edu / student123 (Python Basics - Evening)")
print("                    karthik@institute.edu / student123 (Python Basics - Evening)")

db.close()
