"""All tests available in the bot. Import order is menu order within each category."""

from core.engine import register

from .career import career
from .disc import disc
from .eq import eq
from .jung import jung
from .neo import neo
from .screeners import anxiety, dass_test, depression, ocd
from .strengths import strengths

for inst in (neo, jung, disc, depression, anxiety, dass_test, ocd, eq, career, strengths):
    register(inst)
