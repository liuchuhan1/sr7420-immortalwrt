from pathlib import Path
import json,subprocess,argparse,shlex
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--ucode-command',required=True);a=p.parse_args();s=a.source.read_text(encoding='utf-8-sig')
lo=s[s.index('function resolve_lower_devices('):s.index('function nft_json_command(')]
start=s.index('resolve_hw_offload_devices: function()');res=s[start:s.index('check_set_types: function()',start)]
cases=[
 {'name':'dsa_bridge_software','roots':['br-lan','lan4'],'status':{'br-lan':{'devtype':'bridge'}},'lowers':{'br-lan':['lan1','lan2','lan3']},'expected':['lan1','lan2','lan3','lan4']},
 {'name':'bridge_vlan','roots':['br-lan.10','lan4.20'],'status':{'br-lan.10':{'devtype':'vlan'},'br-lan':{'devtype':'bridge'},'lan4.20':{'devtype':'vlan'}},'lowers':{'br-lan.10':['br-lan'],'br-lan':['lan1','lan2'],'lan4.20':['lan4']},'expected':['lan1','lan2','lan4']},
 {'name':'macvlan_reported_ethernet','roots':['mv0','mv1'],'status':{'mv0':{'type':'macvlan','devtype':'ethernet'},'mv1':{'type':'macvlan','devtype':'ethernet'}},'lowers':{'mv0':['lan4'],'mv1':['lan4']},'expected':['lan4']},
 {'name':'software_veth_retained','roots':['br-lan','lan4'],'status':{'br-lan':{'devtype':'bridge'}},'lowers':{'br-lan':['lan1','veth0']},'expected':['lan1','lan4','veth0']},
 {'name':'removed_device_ignored','roots':['lan1','deleted0'],'missing':['deleted0'],'expected':['lan1']},
 {'name':'deduplicate','roots':['lan1','lan4','lan4'],'expected':['lan1','lan4']},
 {'name':'offload_disabled','roots':['lan1','lan4'],'sw':False,'expected':[]},
 {'name':'no_zones','roots':[],'expected':[]},
 {'name':'no_ubus','roots':['lan1','lan4'],'bus':False,'expected':['lan1','lan4']},
 {'name':'hardware_fallback_still_resolves_bridge','roots':['br-lan','lan4'],'status':{'br-lan':{'devtype':'bridge'}},'lowers':{'br-lan':['lan1','veth0']},'hw':True,'capable':[],'expected':['lan1','lan4','veth0'],'expected_hw':False},
 {'name':'hardware_success_unchanged','roots':['br-lan','lan4'],'status':{'br-lan':{'devtype':'bridge'}},'lowers':{'br-lan':['lan1','veth0']},'hw':True,'capable':['lan1','lan4'],'expected':['lan1','lan4'],'expected_hw':True},
 {'name':'software_ppp_device_retained','roots':['lan1','pppoe-wan'],'expected':['lan1','pppoe-wan']}
]
program='let cases = '+json.dumps(cases)+';'+chr(10)+'''
let current;
let fs={access:path=>index(current.missing||[],substr(path,15))<0,opendir:function(path){
 let n=substr(path,15);if(index(current.missing||[],n)>=0)return null;
 let es=map(current.lowers?.[n]||[],x=>'lower_'+x),i=0;return {read:()=>es[i++]??null,close:()=>true};
}};
let ubus={connect:()=>current.bus===false?null:{call:()=>current.status||{},disconnect:()=>true}};
function nft_try_hw_offload(ds){for(let d in ds)if(index(current.capable||[],d)<0)return false;return length(ds)>0;}
'''+lo+chr(10)+'let target={'+chr(10)+res+'''
state:{},default_option:function(n){return this.state.defaults[n];},zones:()=>[{related_physdevs:current.roots}],warn:()=>true
};
let failures=0;for(let c in cases){current=c;target.state={defaults:{flow_offloading:c.sw??true,flow_offloading_hw:c.hw??false}};
 let actual=target.resolve_offload_devices(),ok=sprintf('%J',actual)==sprintf('%J',c.expected);
 if(c.expected_hw!=null)ok=ok&&(target.state.defaults.flow_offloading_hw==c.expected_hw);
 print(sprintf('%s %s got=%J expected=%J'+chr(10),ok?'PASS':'FAIL',c.name,actual,c.expected));if(!ok)failures++;
}exit(failures?1:0);
'''
cmd=shlex.split(a.ucode_command)+[program];q=subprocess.run(cmd,capture_output=True,text=True,timeout=30);print(q.stdout,end='');print(q.stderr,end='');assert sum(x.startswith(('PASS ','FAIL ')) for x in q.stdout.splitlines())==len(cases);raise SystemExit(q.returncode)
