"""Resolve ADE20K class ids for excluded surfaces' objects from a model's id2label.

Doing it by label name (not hard-coded ids) keeps it robust across model
variants and lets the lists be tuned in settings. The excluded classes split
into two paint categories so the UI can offer independent "paint anyway"
toggles:
  - openings  → doors & windows (and their coverings): OPENING_KEYWORDS
  - objects   → every other excluded fixture/decor: WALL_OBJECT_KEYWORDS minus
                the openings
"""
from floor_tiling.config.settings import WALL_OBJECT_KEYWORDS, OPENING_KEYWORDS


def _ids_for(id2label: dict, keywords) -> set:
    """Class ids whose label matches any of ``keywords`` (case-insensitive substr)."""
    kws = tuple(k.lower() for k in keywords)
    ids = set()
    for i, label in id2label.items():
        name = str(label).lower()
        if any(k in name for k in kws):
            ids.add(int(i))
    return ids


def opening_class_ids(id2label: dict) -> set:
    """Class ids for doors & windows (and coverings)."""
    return _ids_for(id2label, OPENING_KEYWORDS)


def object_class_ids(id2label: dict) -> set:
    """Class ids for excluded wall objects/fixtures, EXCLUDING openings.

    ``id2label`` maps int id → label string (transformers ``model.config``).
    """
    return _ids_for(id2label, WALL_OBJECT_KEYWORDS) - opening_class_ids(id2label)
