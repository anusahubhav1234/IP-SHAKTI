from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import Benchmark, EvaluationRun, User
from app.services import stats

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def analytics_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The caller's own usage, computed from their documents, conversations and audit trail."""
    return stats.overview(db, user.id)


@router.get("/evaluation")
def analytics_evaluation(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The caller's most recent evaluation run (summary only). `null` until a benchmark has been run."""
    row = db.execute(select(EvaluationRun, Benchmark.name).join(Benchmark, Benchmark.id == EvaluationRun.benchmark_id)
                     .where(EvaluationRun.owner_id == user.id).order_by(EvaluationRun.created_at.desc()).limit(1)).first()
    if row is None:
        return {"latest": None}
    run, name = row
    modes = {k: {kk: vv for kk, vv in v.items() if kk != "items"} for k, v in run.results["modes"].items()}
    return {"latest": {"run_id": str(run.id), "benchmark": name, "created_at": run.created_at.isoformat(),
                       "top_k": run.top_k, "n_questions": run.results["n_questions"],
                       "n_scored": run.results["n_scored"], "modes": modes}}
