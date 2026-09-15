from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.users.models import UserRoleEnum, User


async def seed_superadmin(db: AsyncSession) -> None:

    result =await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))

    if result.scalar_one_or_none() is not None:
        return # already seeded — never silently overwrite an existing superadmin


    superadmin = User(
        username = settings.superadmin_username,
        full_name="Super Administrator",
        hashed_password=hash_password(settings.superadmin_password),
        role=UserRoleEnum.SUPERADMIN,
        created_by_id=None,
    )
    db.add(superadmin)
    await db.commit()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await seed_superadmin(db)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
