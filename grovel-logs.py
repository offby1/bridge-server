import collections

lines = []
lines_by_request_id = collections.defaultdict(list)
next_board_request_ids = []

with open("/Users/not-workme/git-repositories/me/bridge/server/django") as inf:
    for line in inf:
        line = line.rstrip()
        lines.append(line)
        fields = line.split()
        for f in fields:
            if f.startswith("request_id="):
                _, request_id = f.split("=")
                lines_by_request_id[request_id].append(line)
            if (
                f == "details.py(172)"
            ):  # e.g. details.py(172) new_board_view _prez wants the next_board on table 1
                next_board_request_ids.append(request_id)

for request_id in next_board_request_ids:
    print(f"\n{request_id}\n")
    for line in lines_by_request_id[request_id]:
        print(line)
