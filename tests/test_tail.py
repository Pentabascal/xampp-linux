from xampp.tail import Follower, tail


def test_tail_last_lines(tmp_path):
    f = tmp_path / "a.log"
    f.write_text("".join(f"{i}\n" for i in range(1000)))
    out = tail(f, 500)
    assert out.splitlines()[0] == "500"
    assert out.splitlines()[-1] == "999"
    assert len(out.splitlines()) == 500


def test_tail_missing_file(tmp_path):
    assert tail(tmp_path / "nada.log") == ""


def test_follower_reads_appended(tmp_path):
    f = tmp_path / "a.log"
    f.write_text("vieja\n")
    fol = Follower(f)
    assert fol.read_new() == ""
    with f.open("a") as h:
        h.write("nueva\n")
    assert fol.read_new() == "nueva\n"
    assert fol.read_new() == ""


def test_follower_handles_truncate(tmp_path):
    f = tmp_path / "a.log"
    f.write_text("mucho texto antiguo\n")
    fol = Follower(f)
    f.write_text("x\n")
    assert fol.read_new() == "x\n"


def test_follower_missing_then_created(tmp_path):
    f = tmp_path / "a.log"
    fol = Follower(f)
    assert fol.read_new() == ""
    f.write_text("hola\n")
    assert fol.read_new() == "hola\n"
