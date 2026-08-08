"""Adapter interface.

A country adapter has two jobs, deliberately split by cost:

  list_programs()  — cheap, bulk. Enumerates every programme the source knows
                     about, yielding a `Listing` each.
  fetch_detail()   — expensive, per-programme. Pulls the full attribute set
                     (admission requirements, language requirements, exact
                     application periods) from the programme's detail page.

How much of a `Listing` is filled in during the bulk pass is up to the source.
DAAD exposes only summary data in search results, so its listings carry no
fields and the detail page has to be fetched per programme — which the CLI and
server do lazily, only for programmes the user actually opens. Study in NL
returns complete records in the listing, so its listings arrive fully
populated and `fetch_detail` never needs to touch the network.
"""

from __future__ import annotations

from typing import Iterator, Protocol

from ..models import Field, Listing, Program


class Adapter(Protocol):
    id: str        # short adapter key stored in programs.source
    country: str   # ISO-3166 alpha-2

    def list_programs(self, **filters) -> Iterator[Listing]:
        ...

    def fetch_detail(self, program: Program) -> tuple[Program, list[Field]]:
        """Return the programme enriched with detail data, plus its raw fields."""
        ...
