#!/usr/bin/env python3
"""Render src/mongo/config.h from config.h.in using upstream's own compile checks (Linux, no SSL)."""
import json
import sys

sys.path.insert(0, "src/mongo")
import mongo_config_header as m

tmpl, out = sys.argv[1:3]
defs = m.generate_config_header(
    "clang++", "-std=c++20", "{}", "/tmp/mongo_config.log", [], json.dumps({"MONGO_CONFIG_HAVE_HEADER_UNISTD_H": "1"})
)
txt = open(tmpl).read()
for k, v in defs.items():
    txt = txt.replace(k, v)
open(out, "w", newline="\n").write(txt)
