# Justfile Simplification Ideas

**None of these have been done yet.** They are opportunities to simplify the justfile using
newer `just` features; the installed `just` is v1.58.0, so every feature named below is
available. Recipe line numbers move constantly -- grep for the recipe name rather than
trusting them.

## 1. `[working-directory: "project"]` to eliminate `cd project &&`

Biggest win. These recipes all do `cd project && ...` and can use the attribute instead:

- `pytest-test`
- `manage`
- `collectstatic`
- `sp`
- `graph`
- `test` (script)
- `cover` (script)
- `_notests` (script)

Before:
```just
[private]
pytest-test *args:
    cd project && DJANGO_SETTINGS_MODULE={{ TEST_DJANGO_SETTINGS }} uv run pytest {{ args }}
```

After:
```just
[working-directory: "project"]
[private]
pytest-test *args:
    DJANGO_SETTINGS_MODULE={{ TEST_DJANGO_SETTINGS }} uv run pytest {{ args }}
```

For `[script]` recipes, `[working-directory]` also works -- just drop the `cd project` line from the bash body.

## 2. `[confirm]` on destructive recipes

Added in v1.17.0. Supports custom prompt strings.

```just
[confirm: "This will git clean -dxff. Proceed?"]
clean:
    git clean -dxff

[confirm: "This will drop the database. Proceed?"]
drop: die-if-not-local-docker pg-stop pg-start
    ...

[confirm: "This will nuke all Docker containers and volumes. Proceed?"]
docker-nuke: die-if-not-local-docker orb
    ...
```

Keep `die-if-not-local-docker` too -- it checks Docker *context*, while `[confirm]` checks user *intent*.

## 3. `[env()]` attribute to replace inline exports

Added in v1.47.0. Cleaner than inline `VAR=value` prefix on commands.

Before:
```just
pytest-test *args:
    cd project && DJANGO_SETTINGS_MODULE={{ TEST_DJANGO_SETTINGS }} uv run pytest {{ args }}
```

After:
```just
[env("DJANGO_SETTINGS_MODULE", TEST_DJANGO_SETTINGS)]
[working-directory: "project"]
pytest-test *args:
    uv run pytest {{ args }}
```

## 4. `read()` to simplify `_deploy` and `_notests`

Added in v1.39.0. Reads file contents at just-expression time, replacing bash `$(cat ...)` subshells.

Before (in `_deploy`):
```bash
export DJANGO_SECRET_KEY=$(cat "${DJANGO_SECRET_FILE}")
export GIT_VERSION="$(cat project/VERSION)"
```

After:
```bash
export DJANGO_SECRET_KEY="{{ read(DJANGO_SECRET_FILE) }}"
export GIT_VERSION="{{ read("project/VERSION") }}"
```

`_notests` reads the same files the same way, so it gets the same treatment. The
Google OAuth pair there is optional, though (`cat ... || echo ""`), and `read()` on a
missing file is an error -- so those two would need a guard, or to stay as they are.

## 5. `[default]` attribute

Added in v1.43.0. Minor cosmetic improvement.

Before:
```just
[private]
default:
    just --list
```

After:
```just
[default]
[private]
_list:
    just --list
```

Makes intent explicit regardless of recipe name.

## 6. `require()` for tool dependencies

Added in v1.39.0. Gives clear early errors when tools are missing.

```just
_ := require("uv")
_ := require("docker")
```

Or conditionally:
```just
orb:
    {{ if os() == "macos" { require("orbctl") } else { "" } }}
    ...
```

## Summary

| Change | Effort | Impact |
|---|---|---|
| `[working-directory: "project"]` | Low | High -- removes `cd project &&` from ~8 recipes |
| `[confirm]` on `clean`/`drop`/`nuke` | Low | Medium -- safety net for destructive ops |
| `[env()]` on `pytest-test` | Low | Small -- but cleaner |
| `read()` in `_deploy`/`_notests` | Low | Medium -- eliminates bash `cat` subshells |
| `[default]` | Trivial | Trivial -- cosmetic |
| `require()` for tools | Low | Small -- better error messages |
