#!/usr/bin/env python3
"""Let LuCI radio device labels use an optional UCI description; keep SSIDs intact."""
from pathlib import Path
import re
MARKER = '/* SR7420: per-radio display label */'
INSERT = MARKER + "const description=this.get('description');if(typeof description==='string'&&description.trim())return description;"
PATTERN = re.compile(r"(getI18n\s*\(\s*\)\s*\{\s*)(?=(?:const|var|let)\s+hw\s*=\s*this\.ubus\(\s*['\"]dev['\"]\s*,\s*['\"]iwinfo['\"]\s*,\s*['\"]hardware['\"]\s*\))")
def patch_text(text):
    if MARKER in text:
        assert text.count(MARKER) == 1 and INSERT in text, 'Unexpected existing LuCI radio label patch'
        return text
    assert len(PATTERN.findall(text)) == 1, 'Expected one LuCI radio hardware description method'
    return PATTERN.sub(lambda match: match[1] + INSERT, text, count=1)
def patch_file(path):
    path = Path(path)
    original = path.read_text()
    modified = patch_text(original)
    if modified != original:
        path.write_text(modified, newline='\n')

# LuCI derives every class module URL from the luci.js query version.
# A header change invalidates old network.js copies without clearing user data.
ASSET_SUFFIX = '-sr7420-radio-labels-1'
HEADER_PATTERN = re.compile(r'(<script\s+src="[^"\r\n]*/luci\.js\?v=)([^"\r\n]+)(?=")')

def patch_header_text(text):
    matches = list(HEADER_PATTERN.finditer(text))
    assert len(matches) == 1, 'Expected one versioned LuCI loader in the header'
    match = matches[0]
    if ASSET_SUFFIX in text:
        assert text.count(ASSET_SUFFIX) == 1 and match.group(2).endswith(ASSET_SUFFIX), 'Unexpected LuCI asset version patch'
        return text
    return text[:match.end(2)] + ASSET_SUFFIX + text[match.end(2):]

def patch_header_file(path):
    path = Path(path)
    original = path.read_text()
    modified = patch_header_text(original)
    if modified != original:
        path.write_text(modified, newline='\n')
