#!/usr/bin/env python3
from helpers.text_extraction import extract_text_from_bytes
from helpers.section_segmentation import split_into_sections
from helpers.field_extraction import assemble_full_schema

with open("resume.pdf","rb") as f:
    data = f.read()

txt = extract_text_from_bytes("sample.pdf", data)
secs = split_into_sections(txt)
schema = assemble_full_schema(txt, secs)

import json
print(json.dumps(schema, indent=2)[:2000])
