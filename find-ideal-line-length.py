import collections
import pathlib
import subprocess
import tomlkit

qualities_by_line_length = collections.defaultdict(float)

cwd = pathlib.Path(__file__).parent.resolve()


def edit_precommit_file(candidate_length):
    fn = cwd / "pyproject.toml"
    with open(fn, "rb") as inf:
        parsed = tomlkit.load(inf)

    try:
        tool = parsed["tool"]
    except Exception as e:
        import pprint

        print(e)
        pprint.pprint(parsed)
        exit(1)
    tool["ruff"]["line-length"] = candidate_length

    with open(fn, "w") as inf:
        tomlkit.dump(parsed, inf)


def restore_project():
    subprocess.run(["git", "restore", "."], check=True, cwd=cwd)


def reformat_project(candidate_length):
    restore_project()
    edit_precommit_file(candidate_length)
    subprocess.run(["pre-commit", "run", "--all"], check=False, cwd=cwd, stdout=subprocess.DEVNULL)


def diff_project():
    child = subprocess.run(["git", "diff"], check=False, cwd=cwd, capture_output=True)
    return child.stdout


def value_deltas(deltas):
    return -deltas.count(b"\n")


if __name__ == "__main__":
    try:
        for candidate_length in range(80, 121):
            print(f"{candidate_length=}... ", end="")
            reformat_project(candidate_length)
            deltas = diff_project()
            quality = value_deltas(deltas)
            qualities_by_line_length[candidate_length] = quality
            print(f"done: {quality}")

        import pprint

        pprint.pprint(dict(qualities_by_line_length))
    finally:
        restore_project()
