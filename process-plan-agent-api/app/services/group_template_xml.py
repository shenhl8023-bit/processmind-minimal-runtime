from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from lxml import etree


MAX_GROUP_TEMPLATE_BYTES = 5 * 1024 * 1024
FEATURE_DICTIONARY_PATH = Path(__file__).parents[1] / "assets" / "group_templates" / "FeatureTemplate.xml"

_ENCODING_DECLARATION = re.compile(
    rb"<\?xml\b[^>]*\bencoding\s*=\s*['\"]\s*([A-Za-z0-9._-]+)\s*['\"]",
    re.IGNORECASE,
)
_XML_DECLARATION = re.compile(r"^\s*<\?xml\b[^?]*\?>", re.IGNORECASE)
_XML_DECLARATION_ENCODING = re.compile(
    r"(encoding\s*=\s*['\"])[^'\"]+(['\"])", re.IGNORECASE
)


@dataclass(frozen=True)
class GroupTemplateParseIssue:
    code: str
    message: str
    path: list[str] = field(default_factory=list)
    value: str = ""


@dataclass
class GroupTemplateParseResult:
    original_filename: str
    source_encoding: str
    part_filename: str
    content_hash: str
    feature_dictionary_version: str
    source_xml: str
    tree: list[dict[str, object]] = field(default_factory=list)
    issues: list[GroupTemplateParseIssue] = field(default_factory=list)
    group_count: int = 0
    feature_selection_count: int = 0

    @property
    def can_confirm(self) -> bool:
        return not self.issues


def normalize_name(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())


def stable_group_key(path: list[str]) -> str:
    canonical = json.dumps(path, ensure_ascii=False, separators=(",", ":"))
    return f"grp_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def parse_group_template_xml(filename: str, payload: bytes) -> GroupTemplateParseResult:
    content_hash = hashlib.sha256(payload).hexdigest()
    dictionary_version = _feature_dictionary_version()
    result = GroupTemplateParseResult(
        original_filename=filename,
        source_encoding="",
        part_filename="",
        content_hash=content_hash,
        feature_dictionary_version=dictionary_version,
        source_xml="",
    )

    if not filename.lower().endswith(".xml"):
        return _add_issue(result, "invalid_file_extension", "Only .xml group templates are accepted.")
    if len(payload) > MAX_GROUP_TEMPLATE_BYTES:
        return _add_issue(result, "payload_too_large", "Group template payload exceeds 5 MiB.")
    if re.search(rb"<!\s*(doctype|entity)\b", payload, re.IGNORECASE):
        return _add_issue(result, "unsafe_xml_declaration", "DOCTYPE and ENTITY declarations are not allowed.")

    source_xml, source_encoding = _decode_xml(payload)
    if source_xml is None:
        return _add_issue(result, "decode_failed", "The XML payload cannot be decoded safely.")
    result.source_encoding = source_encoding
    result.source_xml = _normalize_xml_declaration(source_xml)

    try:
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        )
        root = etree.fromstring(result.source_xml.encode("utf-8"), parser=parser)
    except (etree.XMLSyntaxError, ValueError, UnicodeError):
        return _add_issue(result, "invalid_xml", "The XML document is malformed.")

    if root.tag != "Kmsoft":
        return _add_issue(result, "invalid_root", "The root node must be Kmsoft.")

    root_items = root.findall("./Item")
    if not any(item.get("type") == "Part_Template" for item in root_items):
        return _add_issue(result, "missing_part_template", "Part_Template is required.")
    if not any(item.get("type") == "Group_Template" for item in root_items):
        return _add_issue(result, "missing_group_template", "Group_Template is required.")

    parts = [item for item in root_items if item.get("type") == "Part"]
    if len(parts) != 1:
        return _add_issue(result, "invalid_part_count", "Exactly one Part is required.")

    part = parts[0]
    result.part_filename = normalize_name(part.get("filename"))
    feature_dictionary = _load_feature_dictionary()
    if feature_dictionary is None:
        return _add_issue(result, "feature_dictionary_unavailable", "The feature dictionary cannot be loaded.")

    group_count = 0
    feature_selection_count = 0

    def add_issue(code: str, message: str, path: list[str], value: str = "") -> None:
        result.issues.append(GroupTemplateParseIssue(code, message, path, value))

    def parse_group(group: etree._Element, path: list[str]) -> dict[str, object] | None:
        nonlocal group_count, feature_selection_count
        direct_params = group.findall("./Params/param")
        raw_name = next(
            (param.get("value", "") for param in direct_params if param.get("name") == "名称"),
            "",
        )
        name = normalize_name(raw_name)
        if not name:
            add_issue("blank_group_name", "Every Group requires a non-blank 名称.", path, "")
            return None

        node_path = [*path, name]
        params: dict[str, str] = {}
        feature_values: list[str] = []
        seen_features: set[str] = set()
        for param in direct_params:
            param_name = param.get("name", "")
            value = param.get("value", "")
            if param_name == "名称":
                continue
            if param_name == "特征选择":
                for token in value.split(","):
                    feature = normalize_name(token)
                    if feature and feature not in seen_features:
                        seen_features.add(feature)
                        feature_values.append(feature)
                continue
            params[param_name] = value

        for feature in feature_values:
            if feature not in feature_dictionary:
                add_issue(
                    "unknown_feature_selection",
                    "Feature selection is not present in the approved dictionary.",
                    node_path,
                    feature,
                )

        children: list[dict[str, object]] = []
        sibling_names: set[str] = set()
        for child in group.findall("./Item[@type='Group']"):
            child_name = normalize_name(next(
                (param.get("value", "") for param in child.findall("./Params/param") if param.get("name") == "名称"),
                "",
            ))
            if child_name in sibling_names and child_name:
                add_issue(
                    "duplicate_sibling_name",
                    "Sibling Group names must be unique after normalization.",
                    [*node_path, child_name],
                    child_name,
                )
            sibling_names.add(child_name)
            parsed_child = parse_group(child, node_path)
            if parsed_child is not None:
                children.append(parsed_child)

        group_count += 1
        feature_selection_count += len(feature_values)
        return {
            "key": stable_group_key(node_path),
            "source_id": group.get("id", ""),
            "name": name,
            "path": node_path,
            "feature_selections": feature_values,
            "params": params,
            "children": children,
        }

    tree: list[dict[str, object]] = []
    sibling_names: set[str] = set()
    for group in part.findall("./Item[@type='Group']"):
        group_name = normalize_name(next(
            (param.get("value", "") for param in group.findall("./Params/param") if param.get("name") == "名称"),
            "",
        ))
        if group_name in sibling_names and group_name:
            add_issue(
                "duplicate_sibling_name",
                "Sibling Group names must be unique after normalization.",
                [group_name],
                group_name,
            )
        sibling_names.add(group_name)
        parsed_group = parse_group(group, [])
        if parsed_group is not None:
            tree.append(parsed_group)

    if not tree:
        add_issue("no_groups", "The Part must contain at least one Group.", [])
    result.tree = tree
    result.group_count = group_count
    result.feature_selection_count = feature_selection_count
    return result


def _add_issue(result: GroupTemplateParseResult, code: str, message: str) -> GroupTemplateParseResult:
    result.issues.append(GroupTemplateParseIssue(code, message))
    return result


def _decode_xml(payload: bytes) -> tuple[str | None, str]:
    match = _ENCODING_DECLARATION.search(payload[:4096])
    declared_encoding = match.group(1).decode("ascii") if match else ""
    candidates = [declared_encoding] if declared_encoding else ["utf-8", "gb18030"]
    for candidate in candidates:
        codec = {"gb2312": "gb18030", "gbk": "gb18030"}.get(candidate.lower(), candidate)
        try:
            return payload.decode(codec), declared_encoding or candidate
        except (LookupError, UnicodeDecodeError):
            continue
    return None, declared_encoding


def _normalize_xml_declaration(source_xml: str) -> str:
    declaration = _XML_DECLARATION.match(source_xml)
    if declaration is None:
        return source_xml
    normalized = _XML_DECLARATION_ENCODING.sub(r"\1UTF-8\2", declaration.group(0))
    return f"{normalized}{source_xml[declaration.end():]}"


def _feature_dictionary_version() -> str:
    return hashlib.sha256(FEATURE_DICTIONARY_PATH.read_bytes()).hexdigest()


def _load_feature_dictionary() -> set[str] | None:
    try:
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, recover=False, huge_tree=False)
        root = etree.fromstring(FEATURE_DICTIONARY_PATH.read_bytes(), parser=parser)
    except (OSError, etree.XMLSyntaxError):
        return None
    return {normalize_name(item.get("name")) for item in root.findall(".//Item") if normalize_name(item.get("name"))}
