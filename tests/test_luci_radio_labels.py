#!/usr/bin/env python3
"""Check label patch scope, minified input, idempotence and unchanged SSIDs."""
from pathlib import Path
import sys
repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'tools'))
from luci_radio_labels import patch_text, patch_header_text, INSERT, ASSET_SUFFIX
for method in ["getI18n(){const hw=this.ubus('dev','iwinfo','hardware');return hw.name;}",
               "getI18n() {\n\tconst hw = this.ubus('dev', 'iwinfo', 'hardware'); return hw.name; }"]:
    original = 'getSSID(){return "immortalwrt";},' + method
    patched = patch_text(original)
    assert patched.count(INSERT) == 1 and patched.replace(INSERT, '') == original
    assert patch_text(patched) == patched
    for invalid in ['', original + original]:
        try:
            patch_text(invalid)
        except AssertionError:
            pass
        else:
            raise AssertionError('Unexpected LuCI source shape accepted')
config = (repo / 'files/etc/config/wireless').read_text()
assert config.count("option ssid 'immortalwrt'") == 2
assert "option description 'QCN6224 2.4G'" in config
assert "option description 'QCN6224 5G'" in config
assert "option radio '" not in config
assert config.count("config wifi-device ") == 2
assert 'soc/15202000.pcie/pci0001:00/0001:00:00.0/0001:01:00.0' in config
assert 'soc/15200000.pcie/pci0000:00/0000:00:00.0/0000:01:00.0' in config
print('Per-band LuCI device labels verified; SSIDs unchanged; two independent PCIe radios')

for version in ['{# PKG_VERSION #}-{{ pkgs_update_time }}', '26.304.59036~d438535-{{ pkgs_update_time }}']:
    original = '<script src="{{ resource }}/luci.js?v=' + version + '"></script>'
    patched = patch_header_text(original)
    assert patched.replace(ASSET_SUFFIX, '') == original
    assert patch_header_text(patched) == patched
    for invalid in ['', original + original]:
        try:
            patch_header_text(invalid)
        except AssertionError:
            pass
        else:
            raise AssertionError('Missing or ambiguous LuCI loader accepted')
print('LuCI loader and class module URLs receive a distinct, idempotent asset version')
