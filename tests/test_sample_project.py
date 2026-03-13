from rp_hex_tool.engine import load_project


def test_sample_parts_project_is_valid():
    project = load_project("examples/sample_parts_project.json")
    assert project.name == "Sample Parts SN"
    assert [f.key for f in project.fields] == ["hardware_part_number", "hardware_version_info", "hardware_supplier_info", "ecu_serial_number", "aumovio_pcb_assembly", "hw_compatibility_index", "kml_irk", "kml_vehicle_bt_address", "vhl_wcc"]
