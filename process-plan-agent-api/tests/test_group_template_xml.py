import hashlib
from pathlib import Path

import pytest
from lxml import etree

from app.services.group_template_xml import parse_group_template_xml


SAMPLES = Path(__file__).parent / "fixtures" / "group_templates"


def flatten_nodes(nodes):
    for node in nodes:
        yield node
        yield from flatten_nodes(node["children"])


def xml_bytes(
    *,
    group_id="group-1",
    name="孔",
    feature_selection="孔(盲孔)",
    encoding="utf-8",
    include_part_template=True,
    include_group_template=True,
    parts=1,
    include_group=True,
):
    templates = ""
    if include_part_template:
        templates += '<Item type="Part_Template" />'
    if include_group_template:
        templates += '<Item type="Group_Template" />'
    group = ""
    if include_group:
        group = f'''<Item type="Group" id="{group_id}">
            <Params>
              <param name="名称" value="{name}" />
              <param name="依赖方向" value="从父" />
              <param name="特征选择" value="{feature_selection}" />
            </Params>
          </Item>'''
    part_nodes = "".join(
        f'<Item type="Part" filename="part-{index}.prt">{group}</Item>'
        for index in range(parts)
    )
    text = f'''<?xml version="1.0" encoding="{encoding}"?>
    <Kmsoft>{templates}{part_nodes}</Kmsoft>'''
    codec = "gb18030" if encoding.lower() in {"gb2312", "gbk"} else encoding
    return text.encode(codec)


def duplicate_sibling_xml():
    return '''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" />
      <Item type="Group_Template" />
      <Item type="Part" filename="part.prt">
        <Item type="Group" id="one"><Params><param name="名称" value=" 孔 " /></Params></Item>
        <Item type="Group" id="two"><Params><param name="名称" value="孔" /></Params></Item>
      </Item>
    </Kmsoft>'''.encode("utf-8")


@pytest.mark.parametrize("filename", [
    "临时壳体4.xml",
    "套筒类(未指定参数).xml",
    "套筒类.xml",
    "飞机壁板类1.xml",
    "新衬套模板.xml",
])
def test_parses_real_kmsoft_templates(filename):
    payload = (SAMPLES / filename).read_bytes()
    result = parse_group_template_xml(filename, payload)

    assert result.can_confirm is True
    assert result.group_count > 0
    assert result.content_hash == hashlib.sha256(payload).hexdigest()
    assert all(node["key"].startswith("grp_") for node in flatten_nodes(result.tree))


def test_stable_key_uses_normalized_path_not_xml_id():
    first = parse_group_template_xml("a.xml", xml_bytes(group_id="id-a", name=" 孔 "))
    second = parse_group_template_xml("b.xml", xml_bytes(group_id="id-b", name="孔"))

    assert first.tree[0]["key"] == second.tree[0]["key"]


def test_duplicate_normalized_sibling_name_blocks_confirmation():
    result = parse_group_template_xml("duplicate.xml", duplicate_sibling_xml())

    assert result.can_confirm is False
    assert result.issues[0].code == "duplicate_sibling_name"


def test_rejects_a_second_part_anywhere_in_the_document():
    nested_second_part = '''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" /><Item type="Group_Template" />
      <Item type="Part"><Item type="Group"><Params><param name="名称" value="A侧" /></Params></Item></Item>
      <Item type="Wrapper"><Item type="Part" /></Item>
    </Kmsoft>'''.encode("utf-8")
    result = parse_group_template_xml("multiple-parts.xml", nested_second_part)

    assert result.can_confirm is False
    assert any(issue.code == "invalid_part_count" for issue in result.issues)


def test_discovers_a_group_descendant_behind_a_non_group_wrapper():
    wrapped_group = '''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" /><Item type="Group_Template" />
      <Item type="Part" filename="wrapped.prt"><Item type="Wrapper">
        <Item type="Group" id="wrapped-group"><Params><param name="名称" value="A侧" /></Params></Item>
      </Item></Item>
    </Kmsoft>'''.encode("utf-8")
    result = parse_group_template_xml("wrapped-group.xml", wrapped_group)

    assert result.can_confirm is True
    assert result.group_count == 1
    assert result.tree[0]["path"] == ["A侧"]


@pytest.mark.parametrize("filename,payload,code", [
    ("template.txt", xml_bytes(), "invalid_file_extension"),
    ("template.xml", b"x" * (5 * 1024 * 1024 + 1), "payload_too_large"),
    ("template.xml", b'<?xml version="1.0" encoding="UTF-8"?><Kmsoft>\xff</Kmsoft>', "decode_failed"),
    ("template.xml", b'<?xml version="1.0" encoding="GB2312"?><Kmsoft>\xff</Kmsoft>', "decode_failed"),
    ("template.xml", b'<?xml version="1.0" encoding="GB18030"?><Kmsoft>\xff</Kmsoft>', "decode_failed"),
    ("template.xml", b'<!DOCTYPE Kmsoft><Kmsoft />', "unsafe_xml_declaration"),
    ("template.xml", b'<!ENTITY dangerous "value"><Kmsoft />', "unsafe_xml_declaration"),
    ("template.xml", b'<!DOCTYPE Kmsoft [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><Kmsoft>&xxe;</Kmsoft>', "unsafe_xml_declaration"),
    ("template.xml", b'<WrongRoot />', "invalid_root"),
    ("template.xml", xml_bytes(include_part_template=False), "missing_part_template"),
    ("template.xml", xml_bytes(include_group_template=False), "missing_group_template"),
    ("template.xml", xml_bytes(parts=0), "invalid_part_count"),
    ("template.xml", xml_bytes(parts=2), "invalid_part_count"),
    ("template.xml", xml_bytes(include_group=False), "no_groups"),
    ("template.xml", xml_bytes(name="   "), "blank_group_name"),
])
def test_rejects_invalid_group_templates(filename, payload, code):
    result = parse_group_template_xml(filename, payload)

    assert result.can_confirm is False
    assert any(issue.code == code for issue in result.issues)


def test_decodes_gb2312_gbk_and_gb18030_declarations_case_insensitively():
    for encoding in ("gB2312", "GBK", "gb18030"):
        result = parse_group_template_xml("template.xml", xml_bytes(encoding=encoding))

        assert result.can_confirm is True
        assert result.source_encoding == encoding
        assert 'encoding="UTF-8"' in result.source_xml
        etree.fromstring(result.source_xml.encode("utf-8"))


def test_preserves_group_traceability_params_and_deduplicates_feature_values():
    result = parse_group_template_xml(
        "template.xml",
        xml_bytes(feature_selection=" 孔(盲孔),孔(盲孔), 孔(通孔) "),
    )
    node = result.tree[0]

    assert node["path"] == ["孔"]
    assert node["source_id"] == "group-1"
    assert node["feature_selections"] == ["孔(盲孔)", "孔(通孔)"]
    assert node["params"] == {"依赖方向": "从父"}
    assert result.feature_selection_count == 2


def test_unknown_feature_is_reported_with_its_path_and_value():
    nested = '''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" /><Item type="Group_Template" />
      <Item type="Part"><Item type="Group"><Params><param name="名称" value="A侧" /></Params>
        <Item type="Group"><Params><param name="名称" value="孔" /><param name="特征选择" value="非法特征" /></Params></Item>
      </Item></Item>
    </Kmsoft>'''.encode("utf-8")
    result = parse_group_template_xml("unknown.xml", nested)
    issue = next(issue for issue in result.issues if issue.code == "unknown_feature_selection")

    assert result.can_confirm is False
    assert issue.path == ["A侧", "孔"]
    assert issue.value == "非法特征"
