import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.limiter import limiter
from app.database.session import get_db
from app.evaluation.runner import run_evaluation
from app.models import Benchmark, Document, EvaluationRun, User
from app.schemas.evaluation import (BenchmarkCreate, BenchmarkDetail, BenchmarkItem, BenchmarkOut, RunCreate, RunOut)
from app.services.audit import log_action

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


def _bench_out(b: Benchmark) -> dict:
    return {"id": b.id, "name": b.name, "n_items": len(b.items), "n_scored": sum(1 for i in b.items if i.get("relevant")),
            "created_at": b.created_at}


def _owned_benchmark(db: Session, user: User, bid: uuid.UUID) -> Benchmark:
    b = db.get(Benchmark, bid)
    if b is None or b.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benchmark not found")
    return b


@router.post("/benchmarks", response_model=BenchmarkOut, status_code=status.HTTP_201_CREATED)
def create_benchmark(body: BenchmarkCreate, request: Request, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    ids = {g.document_id for it in body.items for g in it.relevant}
    if ids:
        owned = set(db.scalars(select(Document.id).where(Document.id.in_(ids), Document.owner_id == user.id)).all())
        if owned != ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "A referenced document was not found")
    b = Benchmark(owner_id=user.id, name=body.name.strip(),
                  items=[{"question": it.question.strip(), "language": it.language,
                          "relevant": [{"document_id": str(g.document_id), "page": g.page} for g in it.relevant]}
                         for it in body.items])
    db.add(b)
    log_action(db, action="benchmark.create", user_id=user.id, request=request, details={"items": len(body.items)})
    db.commit()
    return _bench_out(b)


@router.get("/benchmarks", response_model=list[BenchmarkOut])
def list_benchmarks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Benchmark).where(Benchmark.owner_id == user.id).order_by(Benchmark.created_at.desc())).all()
    return [_bench_out(b) for b in rows]


@router.get("/benchmarks/{bid}", response_model=BenchmarkDetail)
def get_benchmark(bid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = _owned_benchmark(db, user, bid)
    return {**_bench_out(b), "items": [BenchmarkItem.model_validate({**i, "relevant": [
        {"document_id": g["document_id"], "page": g.get("page")} for g in i["relevant"]]}) for i in b.items]}


@router.delete("/benchmarks/{bid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_benchmark(bid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_owned_benchmark(db, user, bid))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def create_run(request: Request, body: RunCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs the benchmark through the production retriever for each requested mode and stores real measurements."""
    b = _owned_benchmark(db, user, body.benchmark_id)
    if not any(i.get("relevant") for i in b.items):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The benchmark has no questions with gold passages")
    results = run_evaluation(db, user.id, b.items, list(dict.fromkeys(body.modes)), body.top_k)
    run = EvaluationRun(benchmark_id=b.id, owner_id=user.id, top_k=body.top_k, results=results)
    db.add(run)
    log_action(db, action="evaluation.run", user_id=user.id, request=request, details={"modes": body.modes, "top_k": body.top_k})
    db.commit()
    return RunOut(id=run.id, benchmark_id=b.id, benchmark_name=b.name, top_k=run.top_k, created_at=run.created_at, results=run.results)


@router.get("/runs", response_model=list[RunOut])
def list_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(EvaluationRun, Benchmark.name).join(Benchmark, Benchmark.id == EvaluationRun.benchmark_id)
                      .where(EvaluationRun.owner_id == user.id).order_by(EvaluationRun.created_at.desc()).limit(50)).all()
    return [RunOut(id=r.id, benchmark_id=r.benchmark_id, benchmark_name=n, top_k=r.top_k, created_at=r.created_at,
                   results={**r.results, "modes": {k: {kk: vv for kk, vv in v.items() if kk != "items"} for k, v in r.results["modes"].items()}})
            for r, n in rows]


@router.get("/runs/{rid}", response_model=RunOut)
def get_run(rid: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(EvaluationRun, rid)
    if r is None or r.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    b = db.get(Benchmark, r.benchmark_id)
    return RunOut(id=r.id, benchmark_id=r.benchmark_id, benchmark_name=b.name if b else None, top_k=r.top_k,
                  created_at=r.created_at, results=r.results)
