import enum
import uuid
from datetime import date, datetime




class UserRole(str, enum.Enum):
    assistant = "assistant"
    manager = "manager"
    superadmin = "superadmin"



class UserStatus(str, enum.Enum):
    pending = "pending"      # ro'yxatdan o'tdi, manager/superadmin tasdig'ini kutmoqda
    approved = "approved"    # tasdiqlangan, to'liq ishlay oladi
    rejected = "rejected"    # manager/superadmin rad etdi
    blocked = "blocked"      # manager/superadmin blokladi
