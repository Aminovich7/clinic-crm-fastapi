from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# Postgres NUMERIC values round-tripped through asyncpg can come back as a
# Decimal with a different internal exponent than how they were written
# (e.g. coefficient 1, exponent 5 for "100000"), which Python's default
# str(Decimal) renders in scientific notation ("1E+5"). Fixed-point ("f")
# formatting always renders the full digit string instead.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]
