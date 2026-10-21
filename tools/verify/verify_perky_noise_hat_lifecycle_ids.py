#!/usr/bin/env python3
"""Execute the actual observer's ID extension at two wire-sequence wraps."""
import json,subprocess
from pathlib import Path
import build_perky_noise_hat_lifecycle_observer as b
def main():
 w=b.WORK;receipt=json.loads((w/'observer/OBSERVER_BUILD.json').read_text())
 source=w/'wire-ids.cpp';binary=w/'wire-ids'
 # Release compiler flags include NDEBUG: use executable checks, not assert.
 source.write_text('#include "'+str(w/'lifecycle-observer.h')+'"\n#include <iostream>\nint main(){nht_lifecycle_base::Observer o;unsigned cases=0;for(unsigned start:{1u,65528u,131064u})for(unsigned seq=start;seq<start+(start==1?32:25);seq++){o.seq=seq;for(unsigned age=0;age<8&&age<seq;age++){if(o.unwrap((seq-age)&65535u)!=seq-age)return 1;cases++;}}if(cases!=628)return 2;std::cout<<cases<<" wire IDs passed\\n";}\n')
 command=receipt['commands'][0];flags=command[:command.index('-c')]
 compile=[*flags,str(source),'-o',str(binary)];subprocess.run(compile,check=True)
 subprocess.run([str(binary)],check=True)
 report=dict(status='PASS_ACTUAL_COMPILED_OBSERVER_ID_EXTENSION',vectors=628,
  source_sha256=b.b.base.sha(source),generated_header_sha256=b.b.base.sha(w/'lifecycle-observer.h'),binary_sha256=b.b.base.sha(binary),command=compile)
 (w/'WIRE_IDS.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
