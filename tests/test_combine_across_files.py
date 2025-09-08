import os
from hh_tools.extract_timeseries import combine_across_files

def test_combine_across_files_handles_empty(tmp_path):
    f1 = tmp_path / "a.tsf"
    f2 = tmp_path / "b.tsf"
    header = "IDs:\tX\nDate/Time\tFlow\n"
    f1.write_text(header)
    f2.write_text(header)

    combine_across_files([("node", str(f1)), ("node", str(f2))], "tsf", str(tmp_path))

    # No combined output should be produced and, crucially, no exception
    assert not (tmp_path / "combined").exists()
