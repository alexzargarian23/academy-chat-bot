from fastapi import APIRouter, Depends

from app.core.permissions import require_roles
from app.models import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard")
def admin_dashboard(
    current_user: User = Depends(require_roles("admin"))
):
    return {
        "message": "Welcome to the admin dashboard",
        "user": current_user.full_name
    }