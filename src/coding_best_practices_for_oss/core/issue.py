# Issue/Finding dataclass (severity, message, location...)
#
# Rules never build report dictionaries by hand: they return `Issue` objects and
# the serialisation to the formats supported by the action lives here.
#   - "generic" -> SonarQube generic issue import format
#   - "sarif"   -> SARIF 2.1.0 result objects
#
# Column convention: columns are stored 1-based (the SARIF convention) and
# converted to 0-based when emitting the SonarQube generic format.
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Issue severity, using the SonarQube severity vocabulary."""

    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"
    BLOCKER = "BLOCKER"

    @classmethod
    def parse(cls, value: "str | Severity") -> "Severity":
        """Accept a `Severity` or a (case-insensitive) string such as "minor"."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError as exc:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(f"Unknown severity {value!r}, expected one of: {valid}") from exc

    @property
    def sarif_level(self) -> str:
        """SARIF `level` matching this severity."""
        return {
            Severity.INFO: "note",
            Severity.MINOR: "warning",
            Severity.MAJOR: "warning",
            Severity.CRITICAL: "error",
            Severity.BLOCKER: "error",
        }[self]

    @property
    def impact_severity(self) -> "ImpactSeverity":
        """Software quality impact severity matching this severity."""
        return {
            Severity.INFO: ImpactSeverity.INFO,
            Severity.MINOR: ImpactSeverity.LOW,
            Severity.MAJOR: ImpactSeverity.MEDIUM,
            Severity.CRITICAL: ImpactSeverity.HIGH,
            Severity.BLOCKER: ImpactSeverity.BLOCKER,
        }[self]


class IssueType(str, Enum):
    """SonarQube issue type."""

    CODE_SMELL = "CODE_SMELL"
    BUG = "BUG"
    VULNERABILITY = "VULNERABILITY"


class SoftwareQuality(str, Enum):
    """Software quality affected by an issue (SonarQube "impacts")."""

    MAINTAINABILITY = "MAINTAINABILITY"
    RELIABILITY = "RELIABILITY"
    SECURITY = "SECURITY"


class ImpactSeverity(str, Enum):
    """Severity of an impact on a software quality."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class Impact:
    """How much an issue hurts one software quality."""

    software_quality: SoftwareQuality
    severity: ImpactSeverity

    def to_generic(self) -> dict[str, str]:
        return {
            "softwareQuality": self.software_quality.value,
            "severity": self.severity.value,
        }


@dataclass(frozen=True)
class Location:
    """Where an issue is reported.

    `file_path` is relative to the checked project root (POSIX separators), so
    that both report formats can reference it as-is. Line/column numbers are
    1-based and optional: project level findings (a missing README, for example)
    are reported on the anchor file without a text range.
    """

    file_path: str
    message: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    start_column: int | None = None
    end_column: int | None = None

    def text_range(self) -> dict[str, int] | None:
        """SonarQube `textRange` (0-based columns), or None without a line."""
        if self.start_line is None:
            return None
        text_range: dict[str, int] = {"startLine": self.start_line}
        if self.end_line is not None:
            text_range["endLine"] = self.end_line
        if self.start_column is not None:
            text_range["startColumn"] = max(self.start_column - 1, 0)
        if self.end_column is not None:
            text_range["endColumn"] = max(self.end_column - 1, 0)
        return text_range

    def region(self) -> dict[str, int] | None:
        """SARIF `region` (1-based columns), or None without a line."""
        if self.start_line is None:
            return None
        region = {
            "startLine": self.start_line,
            "endLine": self.end_line,
            "startColumn": self.start_column,
            "endColumn": self.end_column,
        }
        return {key: value for key, value in region.items() if value is not None}

    def to_generic(self, default_message: str | None = None) -> dict[str, Any]:
        location: dict[str, Any] = {
            "message": self.message or default_message or "",
            "filePath": self.file_path,
        }
        text_range = self.text_range()
        if text_range:
            location["textRange"] = text_range
        return location

    def to_sarif(self) -> dict[str, Any]:
        physical_location: dict[str, Any] = {"artifactLocation": {"uri": self.file_path}}
        region = self.region()
        if region:
            physical_location["region"] = region
        location: dict[str, Any] = {"physicalLocation": physical_location}
        if self.message:
            location["message"] = {"text": self.message}
        return location


@dataclass
class Issue:
    """A single finding reported by a rule.

    Rule level metadata (name, description, help URI) lives on the `Rule` class;
    the reporter builds the `rules` array of the report from the rules that
    produced issues. Severity, type and impacts are carried by the issue because
    they can be overridden per rule through the configuration file.
    """

    rule_id: str
    message: str
    location: Location
    severity: Severity = Severity.MINOR
    issue_type: IssueType = IssueType.CODE_SMELL
    impacts: tuple[Impact, ...] = ()
    secondary_locations: tuple[Location, ...] = ()
    effort_minutes: int | None = None
    engine_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.severity = Severity.parse(self.severity)
        self.impacts = tuple(self.impacts)
        self.secondary_locations = tuple(self.secondary_locations)
        # Default to an impact derived from the severity so that reports always
        # carry at least one, as expected by SonarQube.
        if not self.impacts:
            self.impacts = (
                Impact(
                    _DEFAULT_QUALITY_BY_TYPE[self.issue_type],
                    self.severity.impact_severity,
                ),
            )

    @property
    def file_path(self) -> str:
        return self.location.file_path

    @property
    def sort_key(self) -> tuple[Any, ...]:
        """Stable ordering, so that two runs produce identical reports."""
        return (
            self.location.file_path,
            self.location.start_line or 0,
            self.location.start_column or 0,
            self.rule_id,
            self.message,
        )

    def to_generic(self, engine_id: str | None = None) -> dict[str, Any]:
        """SonarQube generic issue import entry."""
        issue: dict[str, Any] = {
            "ruleId": self.rule_id,
            "engineId": self.engine_id or engine_id or "",
            "primaryLocation": self.location.to_generic(default_message=self.message),
        }
        if self.effort_minutes is not None:
            issue["effortMinutes"] = self.effort_minutes
        if self.secondary_locations:
            issue["secondaryLocations"] = [
                location.to_generic() for location in self.secondary_locations
            ]
        return issue

    def to_sarif(self) -> dict[str, Any]:
        """SARIF 2.1.0 result object."""
        primary_location = self.location.to_sarif()
        # The result already carries the message, no need to repeat it.
        if primary_location.get("message", {}).get("text") == self.message:
            del primary_location["message"]
        result: dict[str, Any] = {
            "ruleId": self.rule_id,
            "level": self.severity.sarif_level,
            "message": {"text": self.message},
            "locations": [primary_location],
        }
        if self.secondary_locations:
            result["relatedLocations"] = [
                location.to_sarif() for location in self.secondary_locations
            ]
        if self.properties:
            result["properties"] = dict(self.properties)
        return result


_DEFAULT_QUALITY_BY_TYPE = {
    IssueType.CODE_SMELL: SoftwareQuality.MAINTAINABILITY,
    IssueType.BUG: SoftwareQuality.RELIABILITY,
    IssueType.VULNERABILITY: SoftwareQuality.SECURITY,
}
