from rp_hex_tool.engine import load_project


def test_sample_parts_project_is_valid():
    project = load_project("examples/sample_parts_project.json")
    assert project.name == "Sample Parts SN"
    assert [f.key for f in project.fields] == ["part_sn", "hw_sn", "sw_sn"]
