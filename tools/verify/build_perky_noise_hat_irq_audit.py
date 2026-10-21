#!/usr/bin/env python3
"""Build a separate live IRQ witness without changing the measured runtime."""
from pathlib import Path
import build_perky_noise_hat_observer as base
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'out/perky/hybrid/noise-hat-irq-audit'
def transform(source):
    header=ROOT/'tools/harness/perky_cf/noise_hat_irq_audit.h'
    source=source.replace('namespace ot\n{','#include "'+str(header)+'"\nnamespace ot\n{',1)
    marker='Core& k = *m_cores[i];\n\t\t\t\t++k.vectorsTaken'
    assert marker in source
    source=source.replace(marker,'Core& k = *m_cores[i];\n                if(i==0 && _vba==0x2c)nha_irq_audit::audit.enter(*k.dsp);\n\t\t\t\t++k.vectorsTaken',1)
    marker='// O9b: a P write outside the shared window'
    source=source.replace(marker,'if(i==0)nha_irq_audit::audit.write(*c.dsp, _area, _off, _val);\n                '+marker,1)
    marker='\t\tc.dsp->execInterpreter();'
    assert source.count(marker)==1
    source=source.replace(marker,marker+'\n        if(i==0)nha_irq_audit::audit.after(*c.dsp);',1)
    marker='\t\tconst auto pc = c.dsp->getPC().toWord();\n\t\tc.pcRing'
    assert marker in source
    source=source.replace(marker,'\t\tconst auto pc = c.dsp->getPC().toWord();\n        nha_irq_audit::audit.audio(*c.dsp,*c.mem,i,pc);\n\t\tc.pcRing',1)
    marker='\t\tfor(auto& w : m_shared)\n\t\t\tw = next();'
    assert source.count(marker)==1
    source=source.replace(marker,marker+'''
        // Diagnostic counterfactual only: four phase words or four AMP blocks.
        // No firmware patch and no default emulator behavior change.
        if(std::getenv("NHA_CLEAR_STOCK_AMP_PHASE") || std::getenv("NHA_CLEAR_STOCK_AMP_BLOCK"))
            for(auto& core : m_cores)
                for(unsigned at : {0x6600u,0x6900u})
                    for(unsigned j=0;j<(std::getenv("NHA_CLEAR_STOCK_AMP_BLOCK")?32u:1u);j++)
                        core->mem->set(dsp56k::MemArea_X,at+j,0);
''',1)
    return source
if __name__=='__main__':base.build(WORK/'observer',transform)
