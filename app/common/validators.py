"""Shared Pydantic validators for the PATCH (`*Update`) schemas.

Every update schema declares its fields as `X | None = None` so that
`model_dump(exclude_unset=True)` can tell "not mentioned" from "set to this
value" — that is what makes a partial update work at all. The cost is that an
explicitly-sent `null` is indistinguishable from a real value at the service
layer, where a bare `setattr` then writes `None` into a NOT NULL column. That
surfaced as a 500 (an IntegrityError from the commit, or a `TypeError` from a
comparison against `None` just before it) where the answer should plainly have
been 422.

`reject_explicit_null` closes that off for the fields whose columns are NOT
NULL. Fields that really are nullable — `doctor_id`, `staff_id`,
`minus_beshming`, `comment`, `hire_date` — are deliberately left out, because
sending `null` for those is a legitimate way to clear them and must keep
working.

Pydantic does not run field validators against default values, so a field the
caller never mentioned still arrives as `None` and stays "unset". Only a
`null` the caller actually typed reaches the validator.
"""

from pydantic import field_validator


def reject_explicit_null(*fields: str):
    """Build a validator rejecting an explicit `null` for `fields`.

    Assign the result to any class attribute on the schema; Pydantic collects
    it by type, not by name::

        class ExpenseUpdate(BaseModel):
            title: str | None = None
            _no_nulls = reject_explicit_null("title")
    """

    def _reject(cls, value, info):
        if value is None:
            raise ValueError(
                f"{info.field_name} cannot be null — omit the field to leave it unchanged"
            )
        return value

    return field_validator(*fields, mode="before")(classmethod(_reject))
