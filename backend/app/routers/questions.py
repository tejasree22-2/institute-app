from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..services import code_runner

router = APIRouter(tags=["questions"])


def _question_list_item(db: Session, q: models.CodingQuestion) -> schemas.QuestionListItemOut:
    tc_count = db.query(models.TestCase).filter(models.TestCase.question_id == q.id).count()
    a_count = db.query(models.Assignment).filter(models.Assignment.question_id == q.id).count()
    return schemas.QuestionListItemOut(
        id=q.id, title=q.title, difficulty=q.difficulty,
        test_case_count=tc_count, assignment_count=a_count, verified_at=q.verified_at,
    )


@router.get("/questions", response_model=list[schemas.QuestionListItemOut])
def list_questions(
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    questions = db.query(models.CodingQuestion).order_by(models.CodingQuestion.created_at.desc()).all()
    return [_question_list_item(db, q) for q in questions]


@router.post("/questions", response_model=schemas.QuestionDetailOut)
def create_question(
    payload: schemas.CreateQuestionRequest,
    db: Session = Depends(get_db),
    instructor: models.User = Depends(auth.require_instructor),
):
    q = models.CodingQuestion(
        title=payload.title,
        difficulty=payload.difficulty,
        description=payload.description,
        starter_code=payload.starter_code,
        reference_solution=payload.reference_solution,
        created_by=instructor.id,
    )
    db.add(q)
    db.flush()
    for i, tc in enumerate(payload.test_cases):
        db.add(models.TestCase(
            question_id=q.id, stdin=tc.stdin, expected_stdout=tc.expected_stdout,
            is_hidden=tc.is_hidden, ordering=i,
        ))
    db.commit()
    db.refresh(q)
    return q


@router.get("/questions/{question_id}", response_model=schemas.QuestionDetailOut)
def get_question(
    question_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return q


@router.put("/questions/{question_id}", response_model=schemas.QuestionDetailOut)
def update_question(
    question_id: int,
    payload: schemas.UpdateQuestionRequest,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(q, field, value)
    q.verified_at = None
    db.commit()
    db.refresh(q)
    return q


@router.delete("/questions/{question_id}")
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    # rows that point at the question go first (Postgres enforces the foreign keys)
    submission_ids = db.query(models.Submission.id).filter(models.Submission.question_id == question_id)
    db.query(models.SubmissionResult).filter(models.SubmissionResult.submission_id.in_(submission_ids)).delete(synchronize_session=False)
    db.query(models.Submission).filter(models.Submission.question_id == question_id).delete(synchronize_session=False)
    db.query(models.Assignment).filter(models.Assignment.question_id == question_id).delete(synchronize_session=False)
    db.query(models.Note).filter(models.Note.question_id == question_id).delete(synchronize_session=False)
    db.delete(q)
    db.commit()
    return {"ok": True}


@router.post("/questions/{question_id}/verify", response_model=schemas.ExecutionResponse)
def verify_question(
    question_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    test_cases = [
        code_runner.TestCaseInput(id=tc.id, stdin=tc.stdin, expected_stdout=tc.expected_stdout, is_hidden=tc.is_hidden)
        for tc in q.test_cases
    ]
    if not test_cases:
        raise HTTPException(status_code=400, detail="Add at least one test case before verifying")

    results = code_runner.run_test_cases(q.reference_solution, test_cases)
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    if passed == total:
        q.verified_at = datetime.now(timezone.utc)
        db.commit()

    return schemas.ExecutionResponse(
        results=[
            schemas.ResultItemOut(
                test_case_id=r.test_case_id, passed=r.passed, hidden=r.hidden,
                actual_output=r.actual_output, error=r.error, runtime_ms=r.runtime_ms,
            ) for r in results
        ],
        summary=schemas.SummaryOut(total=total, passed=passed, failed=total - passed),
    )


@router.post("/questions/{question_id}/test-cases", response_model=schemas.TestCaseOut)
def add_test_case(
    question_id: int,
    payload: schemas.TestCaseIn,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    q = db.get(models.CodingQuestion, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    ordering = db.query(models.TestCase).filter(models.TestCase.question_id == question_id).count()
    tc = models.TestCase(
        question_id=question_id, stdin=payload.stdin, expected_stdout=payload.expected_stdout,
        is_hidden=payload.is_hidden, ordering=ordering,
    )
    db.add(tc)
    q.verified_at = None
    db.commit()
    db.refresh(tc)
    return tc


@router.put("/test-cases/{test_case_id}", response_model=schemas.TestCaseOut)
def update_test_case(
    test_case_id: int,
    payload: schemas.TestCaseIn,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    tc = db.get(models.TestCase, test_case_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    tc.stdin = payload.stdin
    tc.expected_stdout = payload.expected_stdout
    tc.is_hidden = payload.is_hidden
    q = db.get(models.CodingQuestion, tc.question_id)
    if q:
        q.verified_at = None
    db.commit()
    db.refresh(tc)
    return tc


@router.delete("/test-cases/{test_case_id}")
def delete_test_case(
    test_case_id: int,
    db: Session = Depends(get_db),
    _instructor: models.User = Depends(auth.require_instructor),
):
    tc = db.get(models.TestCase, test_case_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    q = db.get(models.CodingQuestion, tc.question_id)
    # past submissions keep their result rows (and pass counts), just no longer linked to the case
    db.query(models.SubmissionResult).filter(models.SubmissionResult.test_case_id == tc.id).update(
        {models.SubmissionResult.test_case_id: None}, synchronize_session=False)
    db.delete(tc)
    if q:
        q.verified_at = None
    db.commit()
    return {"ok": True}
