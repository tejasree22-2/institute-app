from datetime import datetime
from typing import Annotated, Optional, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from .config import settings


# ---- Auth ----
class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class SignupRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    token: str
    user: UserOut


# ---- Users ----
class CreateStudentRequest(BaseModel):
    name: str
    email: str
    password: str


# ---- Batches ----
class CreateBatchRequest(BaseModel):
    name: str


class BatchOut(BaseModel):
    id: int
    name: str
    member_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class BatchMemberOut(BaseModel):
    id: int
    name: str
    email: str


class BatchRefOut(BaseModel):
    id: int
    name: str


class StudentListItemOut(BaseModel):
    id: int
    name: str
    email: str
    created_at: Optional[datetime] = None
    batches: list[BatchRefOut]


class BatchDetailOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    members: list[BatchMemberOut]


class AddStudentRequest(BaseModel):
    student_id: Optional[int] = None
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


# ---- Test cases ----
class TestCaseIn(BaseModel):
    stdin: str = ""
    expected_stdout: str = ""
    is_hidden: bool = False


class TestCaseOut(BaseModel):
    id: int
    stdin: str
    expected_stdout: str
    is_hidden: bool
    ordering: int

    class Config:
        from_attributes = True


# ---- Questions ----
class CreateQuestionRequest(BaseModel):
    title: str
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    description: str = ""
    starter_code: str = ""
    reference_solution: str = ""
    test_cases: list[TestCaseIn] = []


class UpdateQuestionRequest(BaseModel):
    title: Optional[str] = None
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None
    description: Optional[str] = None
    starter_code: Optional[str] = None
    reference_solution: Optional[str] = None


class QuestionListItemOut(BaseModel):
    id: int
    title: str
    difficulty: str
    test_case_count: int
    assignment_count: int
    verified_at: Optional[datetime]

    class Config:
        from_attributes = True


class QuestionDetailOut(BaseModel):
    id: int
    title: str
    difficulty: str
    description: str
    starter_code: str
    reference_solution: str
    language: str
    verified_at: Optional[datetime]
    test_cases: list[TestCaseOut]

    class Config:
        from_attributes = True


class StudentQuestionOut(BaseModel):
    id: int
    title: str
    difficulty: str
    description: str
    starter_code: str
    language: str
    visible_test_cases: list[TestCaseOut]
    student_code: Optional[str] = None


# ---- Execution ----
class RunRequest(BaseModel):
    code: str = Field(max_length=settings.exec_max_code_chars)


class ResultItemOut(BaseModel):
    test_case_id: int
    passed: bool
    hidden: bool
    actual_output: Optional[str] = None
    error: Optional[str] = None
    runtime_ms: int


class SummaryOut(BaseModel):
    total: int
    passed: int
    failed: int


class ExecutionResponse(BaseModel):
    submission_id: Optional[int] = None
    results: list[ResultItemOut]
    summary: SummaryOut


# ---- Assignments ----
class AssignRequest(BaseModel):
    question_id: int
    batch_ids: list[int]


class AssignmentOut(BaseModel):
    id: int
    question_id: int
    batch_id: int
    assigned_at: datetime

    class Config:
        from_attributes = True


# ---- Notes ----
class NoteOut(BaseModel):
    content: str
    updated_at: Optional[datetime] = None


class NoteUpdateRequest(BaseModel):
    content: str


# ---- Worksheets ----
WorksheetFileKind = Literal["topic", "questions", "answers", "extra_questions", "extra_answers"]
# sheets that are answer keys: only reachable through a link issued for exactly that sheet
ANSWER_KINDS = ("answers", "extra_answers")


class WorksheetFileOut(BaseModel):
    kind: str
    original_filename: str
    uploaded_at: datetime
    viewable: bool = False  # synced from the worksheet repo: open as a page instead of downloading
    label: Optional[str] = None  # link text on the repo's subject index

    class Config:
        from_attributes = True


class CreateWorksheetRequest(BaseModel):
    title: str
    description: str = ""


class UpdateWorksheetRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class WorksheetListItemOut(BaseModel):
    id: int
    title: str
    subject: Optional[str] = None
    subject_slug: Optional[str] = None
    file_count: int
    assignment_count: int
    verified_at: Optional[datetime]
    files: list[WorksheetFileOut] = []
    assignments: list["WorksheetBatchSheets"] = []


class WorksheetDetailOut(BaseModel):
    id: int
    title: str
    subject: Optional[str] = None
    subject_slug: Optional[str] = None
    description: str
    verified_at: Optional[datetime]
    files: list[WorksheetFileOut]


class BatchWorksheetOut(BaseModel):
    id: int
    title: str
    subject: Optional[str] = None
    assigned_at: datetime
    kinds: list[str]  # the sheets this batch was given
    files: list[WorksheetFileOut]


class WorksheetBatchSheets(BaseModel):
    batch_id: int
    kinds: list[WorksheetFileKind]


class WorksheetAssignmentsOut(BaseModel):
    batch_ids: list[int]
    assignments: list[WorksheetBatchSheets]


class SetWorksheetAssignmentsRequest(BaseModel):
    # batches left out (or given no kinds) are unassigned
    assignments: list[WorksheetBatchSheets]


class WorksheetSyncFileOut(BaseModel):
    kind: str
    label: Optional[str] = None
    state: str  # in_repo | kept (gone from the repo, the saved copy is used) | missing


class WorksheetSyncItemOut(BaseModel):
    subject: str
    title: str
    worksheet_id: int
    status: str  # new | existing (already in the Library) | not_in_repo (no longer on the repo index)
    files: list[WorksheetSyncFileOut] = []


class WorksheetSyncStatusOut(BaseModel):
    repo_url: str
    running: bool
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None
    added: list[str] = []  # titles of worksheets that were new in the last sync
    items: list[WorksheetSyncItemOut] = []  # every item the last sync checked
    log: list[str] = []


class WorksheetViewLinkOut(BaseModel):
    url: str


class WorksheetAssignRequest(BaseModel):
    worksheet_id: int
    batch_ids: list[int]


class StudentWorksheetOut(BaseModel):
    id: int
    title: str
    subject: Optional[str] = None
    subject_slug: Optional[str] = None
    description: str
    topic_file: Optional[WorksheetFileOut] = None
    questions_file: Optional[WorksheetFileOut] = None
    answers_file: Optional[WorksheetFileOut] = None
    files: list[WorksheetFileOut] = []  # every sheet assigned to this student's batch(es)
    kinds: list[str] = []  # sheets assigned to this student's batch(es)
    completed: bool


# ---- Student tasks ----
class TaskMetadataOut(BaseModel):
    difficulty: Optional[str] = None
    test_case_count: Optional[int] = None
    file_count: Optional[int] = None
    sheets: Optional[list[str]] = None  # worksheet: the sheets assigned to the student
    labels: Optional[dict[str, str]] = None  # worksheet: link text per sheet, as on the repo's index
    subject: Optional[str] = None
    subject_slug: Optional[str] = None
    position: Optional[int] = None


class TaskOut(BaseModel):
    type: str
    id: int
    title: str
    metadata: TaskMetadataOut
    status: str
    status_detail: str
    assigned_at: datetime


# ---- Performance ----
class PerformanceRowOut(BaseModel):
    student_id: int
    name: str
    email: str
    status: str
    status_detail: str
    attempt_count: int
    last_try_at: Optional[datetime] = None


class SheetViewOut(BaseModel):
    view_count: int = 0
    first_viewed_at: Optional[datetime] = None
    last_viewed_at: Optional[datetime] = None


class WorksheetPerformanceRowOut(BaseModel):
    student_id: int
    name: str
    email: str
    sheets: dict[str, SheetViewOut]  # keyed by topic / questions / answers (assigned sheets only)


class WorksheetPerformanceOut(BaseModel):
    kinds: list[str]  # sheets assigned to this batch
    rows: list[WorksheetPerformanceRowOut]


class SubmissionHistoryItemOut(BaseModel):
    id: int
    status: str
    passed_count: int
    total_count: int
    submitted_at: datetime


class StudentSubmissionsOut(BaseModel):
    student: UserOut
    question_id: int
    submissions: list[SubmissionHistoryItemOut]
    latest_code: Optional[str] = None


# WorksheetListItemOut refers to WorksheetBatchSheets, which is defined after it
WorksheetListItemOut.model_rebuild()
