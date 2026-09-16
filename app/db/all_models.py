"""All models registration for Alembic migrations."""

from app.users import models as user_models
from app.staff.models import Staff
from app.finance.models import Consultation, Room, Surgery, SystemSetting
from app.audit.models import AuditLog
from app.duty.models import DutyEntry
from app.salary.models import SalaryPayment
from app.pharmacy.models import PharmacyEntry
from app.expenses.models import Expense
