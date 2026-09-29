from datetime import datetime, timezone
from typing import get_args

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..ratelimit import execution_limiter
from ..services import code_runner, file_store
from .worksheet_content import view_url

router = APIRouter(tags=["student"])


def _status_for(passed_count: int | None, total_count: int | None) -> tuple[str, str]:
    if total_count is None or passed_count is None:
        return "not_started", "Not started"
    if passed_count == total_count and total_count > 0:
        return "all_passed", "All passed"
    if passed_count > 0:
        return "partial", f"{passed_count} of {total_count} passed"
    return "failed", f"0 of {total_count} passed"


def _latest_submission(db: Session, student_id: int, question_id: int):
    return (
        db.query(models.Submission)
        .filter(models.Submission.student_id == student_id, models.Submission.question_id == question_id)
        .order_by(models.Submission.submitted_at.desc())
        .first()
    )


def _assigned_batch_ids(db: Session, student_id: int) -> list[int]:
    return [
        bs.batch_id for bs in
        db.query(models.BatchStudent).filter(models.BatchStudent.student_id == student_id).all()
    ]


@router.get("/me/batches")
def my_batches(
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    batch_ids = _assigned_batch_ids(db, student.id)
    if not batch_ids:
        return []
    batches = db.query(models.Batch).filter(models.Batch.id.in_(batch_ids)).all()
    return [{"id": b.id, "name": b.name} for b in batches]


@router.get("/me/tasks", response_model=list[schemas.TaskOut])
def my_tasks(
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    batch_ids = _assigned_batch_ids(db, student.id)
    if not batch_ids:
        return []

    assignments = (
        db.query(models.Assignment, models.CodingQuestion)
        .join(models.CodingQuestion, models.CodingQuestion.id == models.Assignment.question_id)
        .filter(models.Assignment.batch_id.in_(batch_ids))
        .all()
    )

    # de-dupe: a question assigned to more than one of the student's batches
    seen = {}
    for a, q in assignments:
        if q.id not in seen or a.assigned_at > seen[q.id][0].assigned_at:
            seen[q.id] = (a, q)

    tasks = []
    for a, q in seen.values():
        tc_count = db.query(models.TestCase).filter(models.TestCase.question_id == q.id).count()
        sub = _latest_submission(db, student.id, q.id)
        status, detail = _status_for(sub.passed_count if sub else None, sub.total_count if sub else None)
        tasks.append(schemas.TaskOut(
            type="coding",
            id=q.id,
            title=q.title,
            metadata=schemas.TaskMetadataOut(difficulty=q.difficulty, test_case_count=tc_count),
            status=status,
            status_detail=detail,
            assigned_at=a.assigned_at,
        ))

    worksheet_assignments = (
        db.query(models.WorksheetAssignment, models.WorksheetTask)
        .join(models.WorksheetTask, models.WorksheetTask.id == models.WorksheetAssignment.worksheet_id)
        .filter(models.WorksheetAssignment.batch_id.in_(batch_ids))
        .all()
    )
    seen_ws = {}
    sheets_by_ws = {}
    for a, w in worksheet_assignments:
        if w.id not in seen_ws or a.assigned_at > seen_ws[w.id][0].assigned_at:
            seen_ws[w.id] = (a, w)
        sheets_by_ws.setdefault(w.id, set()).update(a.kind_list)

    for a, w in seen_ws.values():
        present = {f.kind: f for f in w.files}
        sheets = [k for k in WORKSHEET_KINDS if k in sheets_by_ws[w.id] and k in present]
        tasks.append(schemas.TaskOut(
            type="worksheet",
            id=w.id,
            title=w.title,
            metadata=schemas.TaskMetadataOut(
                file_count=len(sheets), sheets=sheets,
                labels={k: present[k].label for k in sheets if present[k].label},
                subject=w.subject, subject_slug=w.subject_slug, position=w.position,
            ),
            status="not_started",
            status_detail=" · ".join(k.capitalize() for k in sheets) or "No sheets yet",
            assigned_at=a.assigned_at,
        ))

    tasks.sort(key=lambda t: t.assigned_at, reverse=True)
    return tasks


def _assert_assigned(db: Session, student: models.User, question_id: int):
    batch_ids = _assigned_batch_ids(db, student.id)
    assigned = (
        db.query(models.Assignment)
        .filter(models.Assignment.question_id == question_id, models.Assignment.batch_id.in_(batch_ids))
        .first()
    )
    if not assigned:
        raise HTTPException(status_code=403, detail="This task is not assigned to you")


@router.get("/me/questions/{question_id}", response_model=schemas.StudentQuestionOut)
def get_my_question(
    question_id: int,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    _assert_assigned(db, student, question_id)

    visible = [tc for tc in q.test_cases if not tc.is_hidden]
    sub = _latest_submission(db, student.id, question_id)

    return schemas.StudentQuestionOut(
        id=q.id, title=q.title, difficulty=q.difficulty, description=q.description,
        starter_code=q.starter_code, language=q.language,
        visible_test_cases=visible,
        student_code=sub.code if sub else None,
    )


@router.post("/me/questions/{question_id}/run", response_model=schemas.ExecutionResponse)
def run_code(
    question_id: int,
    payload: schemas.RunRequest,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    execution_limiter.hit(f"student:{student.id}")
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    _assert_assigned(db, student, question_id)

    visible = [tc for tc in q.test_cases if not tc.is_hidden]
    test_inputs = [
        code_runner.TestCaseInput(id=tc.id, stdin=tc.stdin, expected_stdout=tc.expected_stdout, is_hidden=False)
        for tc in visible
    ]
    results = code_runner.run_test_cases(payload.code, test_inputs)
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    return schemas.ExecutionResponse(
        results=[
            schemas.ResultItemOut(
                test_case_id=r.test_case_id, passed=r.passed, hidden=False,
                actual_output=r.actual_output, error=r.error, runtime_ms=r.runtime_ms,
            ) for r in results
        ],
        summary=schemas.SummaryOut(total=total, passed=passed, failed=total - passed),
    )


@router.post("/me/questions/{question_id}/submit", response_model=schemas.ExecutionResponse)
def submit_code(
    question_id: int,
    payload: schemas.RunRequest,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    execution_limiter.hit(f"student:{student.id}")
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    _assert_assigned(db, student, question_id)

    test_inputs = [
        code_runner.TestCaseInput(id=tc.id, stdin=tc.stdin, expected_stdout=tc.expected_stdout, is_hidden=tc.is_hidden)
        for tc in q.test_cases
    ]
    results = code_runner.run_test_cases(payload.code, test_inputs)
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    if total == 0:
        status = "error"
    elif passed == total:
        status = "all_passed"
    elif passed == 0:
        status = "failed"
    else:
        status = "partial"

    submission = models.Submission(
        student_id=student.id, question_id=question_id, code=payload.code,
        status=status, passed_count=passed, total_count=total,
    )
    db.add(submission)
    db.flush()
    for r in results:
        db.add(models.SubmissionResult(
            submission_id=submission.id, test_case_id=r.test_case_id, passed=r.passed,
            actual_output=r.actual_output, error=r.error, runtime_ms=r.runtime_ms,
        ))
    db.commit()

    student_results = code_runner.strip_hidden_details(results)
    return schemas.ExecutionResponse(
        submission_id=submission.id,
        results=[
            schemas.ResultItemOut(
                test_case_id=r.test_case_id, passed=r.passed, hidden=r.hidden,
                actual_output=r.actual_output, error=r.error, runtime_ms=r.runtime_ms,
            ) for r in student_results
        ],
        summary=schemas.SummaryOut(total=total, passed=passed, failed=total - passed),
    )


@router.get("/me/questions/{question_id}/notes", response_model=schemas.NoteOut)
def get_notes(
    question_id: int,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    note = (
        db.query(models.Note)
        .filter(models.Note.student_id == student.id, models.Note.question_id == question_id)
        .first()
    )
    if not note:
        return schemas.NoteOut(content="", updated_at=None)
    return schemas.NoteOut(content=note.content, updated_at=note.updated_at)


@router.put("/me/questions/{question_id}/notes", response_model=schemas.NoteOut)
def update_notes(
    question_id: int,
    payload: schemas.NoteUpdateRequest,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    note = (
        db.query(models.Note)
        .filter(models.Note.student_id == student.id, models.Note.question_id == question_id)
        .first()
    )
    if not note:
        note = models.Note(student_id=student.id, question_id=question_id, content=payload.content)
        db.add(note)
    else:
        note.content = payload.content
    db.commit()
    db.refresh(note)
    return schemas.NoteOut(content=note.content, updated_at=note.updated_at)


WORKSHEET_KINDS = get_args(schemas.WorksheetFileKind)


def _assigned_sheets(db: Session, student: models.User, worksheet_id: int) -> set[str]:
    """The sheets (topic/questions/answers) any of the student's batches were given; 403 if none."""
    batch_ids = _assigned_batch_ids(db, student.id)
    rows = (
        db.query(models.WorksheetAssignment)
        .filter(models.WorksheetAssignment.worksheet_id == worksheet_id, models.WorksheetAssignment.batch_id.in_(batch_ids))
        .all()
    )
    if not rows:
        raise HTTPException(status_code=403, detail="This worksheet is not assigned to you")
    return {k for a in rows for k in a.kind_list}


def _assert_sheet_assigned(db: Session, student: models.User, worksheet_id: int, kind: str):
    if kind not in _assigned_sheets(db, student, worksheet_id):
        raise HTTPException(status_code=403, detail=f"The {kind} sheet hasn't been assigned to your batch yet")


def _record_sheet_view(db: Session, student: models.User, worksheet_id: int, kind: str):
    now = datetime.now(timezone.utc)
    view = (
        db.query(models.WorksheetSheetView)
        .filter_by(student_id=student.id, worksheet_id=worksheet_id, kind=kind)
        .first()
    )
    if not view:
        view = models.WorksheetSheetView(student_id=student.id, worksheet_id=worksheet_id, kind=kind,
                                         view_count=0, first_viewed_at=now)
        db.add(view)
    view.view_count += 1
    view.last_viewed_at = now
    db.commit()


def _worksheet_progress(db: Session, student_id: int, worksheet_id: int):
    return (
        db.query(models.WorksheetProgress)
        .filter(models.WorksheetProgress.student_id == student_id, models.WorksheetProgress.worksheet_id == worksheet_id)
        .first()
    )


@router.get("/me/worksheets/{worksheet_id}", response_model=schemas.StudentWorksheetOut)
def get_my_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    sheets = _assigned_sheets(db, student, worksheet_id)

    # only the sheets the instructor assigned to the student's batch are sent
    files_by_kind = {f.kind: f for f in w.files if f.kind in sheets}
    progress = _worksheet_progress(db, student.id, worksheet_id)

    return schemas.StudentWorksheetOut(
        id=w.id, title=w.title, subject=w.subject, subject_slug=w.subject_slug, description=w.description,
        topic_file=files_by_kind.get("topic"),
        questions_file=files_by_kind.get("questions"),
        answers_file=files_by_kind.get("answers"),
        files=[files_by_kind[k] for k in WORKSHEET_KINDS if k in files_by_kind],
        kinds=[k for k in WORKSHEET_KINDS if k in files_by_kind],
        completed=bool(progress and progress.completed_at),
    )


@router.get("/me/worksheets/{worksheet_id}/files/{kind}/download")
def download_my_worksheet_file(
    worksheet_id: int,
    kind: schemas.WorksheetFileKind,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    _assert_sheet_assigned(db, student, worksheet_id, kind)
    _record_sheet_view(db, student, worksheet_id, kind)

    record = next((f for f in w.files if f.kind == kind), None)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return file_store.download_response(db, record)


@router.post("/me/worksheets/{worksheet_id}/files/{kind}/view-link", response_model=schemas.WorksheetViewLinkOut)
def my_worksheet_file_view_link(
    worksheet_id: int,
    kind: schemas.WorksheetFileKind,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    _assert_sheet_assigned(db, student, worksheet_id, kind)
    _record_sheet_view(db, student, worksheet_id, kind)
    return schemas.WorksheetViewLinkOut(url=view_url(w, kind, student))


@router.post("/me/worksheets/{worksheet_id}/complete", response_model=schemas.StudentWorksheetOut)
def complete_my_worksheet(
    worksheet_id: int,
    db: Session = Depends(get_db),
    student: models.User = Depends(auth.require_student),
):
    w = db.get(models.WorksheetTask, worksheet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Worksheet not found")
    _assigned_sheets(db, student, worksheet_id)

    progress = _worksheet_progress(db, student.id, worksheet_id)
    if not progress:
        progress = models.WorksheetProgress(student_id=student.id, worksheet_id=worksheet_id)
        db.add(progress)
    progress.completed_at = datetime.now(timezone.utc)
    db.commit()

    return get_my_worksheet(worksheet_id, db, student)
