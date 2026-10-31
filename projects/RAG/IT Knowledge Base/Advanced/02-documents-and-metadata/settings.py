"""
IT Knowledge Base: The Loader's Settings
========================================

Reads kb_settings.toml, which describes the knowledge base export, and checks it before anything is loaded. It
handles:
  1. KBSettings: which column holds each field, which fields are the Document's text and which its labels, what an
     ID is made from, and one spelling for each label value
  2. load_settings(): the file read and checked; a typo or a missing setting stops the run with one clear line

    load_settings(Path("kb_settings.toml"))  ->  KBSettings(text_fields=("title", ...), columns={"title": "title", ...})
"""
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from article import ARTICLE_FIELDS, REQUIRED_FIELDS, Priority, describe
from utils import spelling_key

# Fields an ID can be made from, and labels that can have a table of spellings: those holding one piece of text
TEXT_LIKE_FIELDS = tuple(name for name in ARTICLE_FIELDS if name not in ("id", "tags"))


class KBSettings(BaseModel):
    """What the knowledge base export holds, and how its articles become Documents."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    text_fields: tuple[str, ...]                        # the Document's text (page_content), in this order
    label_fields: tuple[str, ...]                       # the Document's labels (metadata)
    id_fields: tuple[str, ...]                          # what an ID is made from when the export has no id column
    columns: dict[str, str]                             # each field -> the export's column that holds it
    spellings: dict[str, dict[str, list[str]]] = {}     # a label -> {right spelling: [other spellings]}

    @model_validator(mode="after")
    def _check(self) -> "KBSettings":
        """Every name is a field an article has, the required fields have a column, and no spelling is ambiguous."""
        for setting, names in [("text_fields", self.text_fields), ("label_fields", self.label_fields),
                               ("id_fields", self.id_fields), ("columns", tuple(self.columns)),
                               ("spellings", tuple(self.spellings))]:
            unknown = [name for name in names if name not in ARTICLE_FIELDS]
            if unknown:
                raise ValueError(f"{setting} names a field an article doesn't have ({', '.join(unknown)}); "
                                 f"the fields are {', '.join(ARTICLE_FIELDS)}")
        missing = [name for name in REQUIRED_FIELDS if name not in self.columns]
        if missing:
            raise ValueError(f"columns gives no column for a required field ({', '.join(missing)})")
        shared = sorted({column for column in self.columns.values() if list(self.columns.values()).count(column) > 1})
        if shared:
            raise ValueError(f"columns reads two fields from one column ({', '.join(shared)})")
        if not self.id_fields or any(name not in TEXT_LIKE_FIELDS for name in self.id_fields):
            raise ValueError(f"id_fields must name one or more of {', '.join(TEXT_LIKE_FIELDS)}")
        for label, table in self.spellings.items():
            if label not in TEXT_LIKE_FIELDS:
                raise ValueError(f"spellings.{label}: only {', '.join(TEXT_LIKE_FIELDS)} can have spellings")
            if label == "priority" and set(table) - set(Priority):
                raise ValueError(f"spellings.priority: a right spelling must be one of {', '.join(Priority)}")
            claimed: dict[str, str] = {}
            for right, others in table.items():
                for spelling in (right, *others):
                    key = spelling_key(spelling)
                    if claimed.setdefault(key, right) != right:
                        raise ValueError(f'spellings.{label}: "{spelling}" is a spelling of both "{claimed[key]}" '
                                         f'and "{right}"')
        return self


def load_settings(path: Path) -> KBSettings:
    """
    Read and check the settings file.

    Raises:
        FileNotFoundError: there's no file at path
        ValueError: it isn't valid TOML, or a setting is missing, unknown or wrong (the message says which)
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Settings file not found: {path}")
    try:
        with open(path, "rb") as file:
            return KBSettings.model_validate(tomllib.load(file))
    except tomllib.TOMLDecodeError as err:
        raise ValueError(f"Settings file isn't valid TOML ({err}): {path}") from None
    except ValidationError as err:
        raise ValueError(f"Settings file has a bad setting ({describe(err)}): {path}") from None
