"""All models registration for Alembic migrations."""

from app.users import models as user_models
from app.doctors.models import Doctor
from app.finance.models import Consultation, Room, Surgery, SystemSetting
from app.audit.models import AuditLog



