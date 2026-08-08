from .daad_de import DaadAdapter
from .studyinnl_nl import StudyInNlAdapter

# Keyed by the country code used on the command line and in programs.country.
ADAPTERS = {
    "de": DaadAdapter,
    "nl": StudyInNlAdapter,
}

__all__ = ["ADAPTERS", "DaadAdapter", "StudyInNlAdapter"]
