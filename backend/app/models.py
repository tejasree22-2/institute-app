from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, ForeignKey, DateTime, LargeBinary, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'instructor' | 'student'
    created_at = Column(DateTime, default=now)


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)

    students = relationship("BatchStudent", back_populates="batch", cascade="all, delete-orphan")


class BatchStudent(Base):
    __tablename__ = "batch_students"

    batch_id = Column(Integer, ForeignKey("batches.id"), primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    batch = relationship("Batch", back_populates="students")
    student = relationship("User")


class CodingQuestion(Base):
    __tablename__ = "coding_questions"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    difficulty = Column(String, nullable=False, default="easy")  # easy|medium|hard
    starter_code = Column(Text, nullable=False, default="")
    reference_solution = Column(Text, nullable=False, default="")
    language = Column(String, nullable=False, default="python")
    verified_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    test_cases = relationship(
        "TestCase", back_populates="question",
        cascade="all, delete-orphan", order_by="TestCase.ordering"
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("coding_questions.id", ondelete="CASCADE"))
    stdin = Column(Text, nullable=False, default="")
    expected_stdout = Column(Text, nullable=False, default="")
    is_hidden = Column(Boolean, nullable=False, default=False)
    ordering = Column(Integer, nullable=False, default=0)

    question = relationship("CodingQuestion", back_populates="test_cases")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("question_id", "batch_id"),)

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("coding_questions.id"))
    batch_id = Column(Integer, ForeignKey("batches.id"))
    assigned_at = Column(DateTime, default=now)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer, ForeignKey("coding_questions.id"))
    code = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False)  # all_passed|partial|failed|error
    passed_count = Column(Integer, nullable=False, default=0)
    total_count = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, default=now)

    results = relationship("SubmissionResult", cascade="all, delete-orphan")


class SubmissionResult(Base):
    __tablename__ = "submission_results"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"))
    test_case_id = Column(Integer, ForeignKey("test_cases.id"))
    passed = Column(Boolean, nullable=False, default=False)
    actual_output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    runtime_ms = Column(Integer, nullable=True)


class WorksheetTask(Base):
    __tablename__ = "worksheet_tasks"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    # set for worksheets imported by scripts/sync_worksheets.py; null for hand-uploaded ones
    subject = Column(String, nullable=True)
    subject_slug = Column(String, nullable=True)
    source_key = Column(String, nullable=True, index=True)
    position = Column(Integer, nullable=False, default=0)
    verified_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    files = relationship("WorksheetFile", back_populates="worksheet", cascade="all, delete-orphan")


class WorksheetFile(Base):
    __tablename__ = "worksheet_files"
    __table_args__ = (UniqueConstraint("worksheet_id", "kind"),)

    id = Column(Integer, primary_key=True)
    worksheet_id = Column(Integer, ForeignKey("worksheet_tasks.id", ondelete="CASCADE"))
    kind = Column(String, nullable=False)  # topic | questions | answers | extra_questions | extra_answers
    original_filename = Column(String, nullable=False)
    # key of the file's bytes in stored_files (services/file_store.py)
    stored_path = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    # path inside the synced repo mirror (served as web pages, see routers/worksheet_content.py); null for uploads
    rel_path = Column(String, nullable=True)
    # link text on the repo's subject index ("Questions", "Question Paper", "ans", ...); null for uploads
    label = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=now)

    worksheet = relationship("WorksheetTask", back_populates="files")

    @property
    def viewable(self) -> bool:
        return self.rel_path is not None


class WorksheetAssignment(Base):
    __tablename__ = "worksheet_assignments"
    __table_args__ = (UniqueConstraint("worksheet_id", "batch_id"),)

    id = Column(Integer, primary_key=True)
    worksheet_id = Column(Integer, ForeignKey("worksheet_tasks.id"))
    batch_id = Column(Integer, ForeignKey("batches.id"))
    # which sheets this batch gets, comma-separated subset of the worksheet's file kinds
    kinds = Column(String, nullable=False, default="topic,questions,answers")
    assigned_at = Column(DateTime, default=now)

    @property
    def kind_list(self) -> list[str]:
        return [k for k in (self.kinds or "").split(",") if k]


class WorksheetProgress(Base):
    __tablename__ = "worksheet_progress"
    __table_args__ = (UniqueConstraint("student_id", "worksheet_id"),)

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    worksheet_id = Column(Integer, ForeignKey("worksheet_tasks.id"))
    completed_at = Column(DateTime, nullable=True)


class WorksheetSheetView(Base):
    """A student opening one sheet (topic / questions / answers) of a worksheet; feeds Performance."""
    __tablename__ = "worksheet_sheet_views"
    __table_args__ = (UniqueConstraint("student_id", "worksheet_id", "kind"),)

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    worksheet_id = Column(Integer, ForeignKey("worksheet_tasks.id"))
    kind = Column(String, nullable=False)
    view_count = Column(Integer, nullable=False, default=0)
    first_viewed_at = Column(DateTime, default=now)
    last_viewed_at = Column(DateTime, default=now)


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (UniqueConstraint("student_id", "question_id"),)

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("users.id"))
    question_id = Column(Integer, ForeignKey("coding_questions.id"))
    content = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=now, onupdate=now)


class StoredFile(Base):
    """File bytes kept in the database (uploads and the synced worksheet repo mirror), so the API
    keeps nothing on local disk and runs on hosts whose disk is wiped on every restart."""
    __tablename__ = "stored_files"

    key = Column(String, primary_key=True)  # "uploads/<worksheet id>/<name>" or "content/<subject>/<path>"
    data = Column(LargeBinary, nullable=False)
    content_type = Column(String, nullable=True)
    # the source's ETag for synced files: the next sync asks "changed since?" and skips unchanged downloads
    etag = Column(String, nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)
