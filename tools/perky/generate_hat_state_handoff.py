"""Replace the generated steady CF Hat shadow with snapshot/on-demand replay."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def once(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new,1)

def transform(work,text):
    work=Path(work)
    previous=work/'full-map-shadow.h'
    shadow=previous.read_text()
    # Preserve the already-qualified production CF rendering/import path.
    cf=shadow[shadow.index('static void nhb_cf_frame('):]
    target=work/'full-map-state-handoff.h'
    template=ROOT/'tools/harness/perky_cf/hat_state_handoff.h'
    state=once(template.read_text(),
               '    pk_nhb_produced=pk_nhb_completed=0;pk_budget_cache_clear();',
               '    nhr_last_consumed=0;nhr_last_consumed_valid=0;pk_nhr_mail[0]=0;\n'
               '    pk_nhb_produced=pk_nhb_completed=0;pk_budget_cache_clear();')
    target.write_text(state+'\n'+cf)
    text=once(text,'static unsigned nhr_last_consumed;',
              'static unsigned nhr_last_consumed,nhr_last_consumed_valid;')
    text=once(text,'if(nhr_last_consumed && (nhr_last_consumed&65535)==sequence)return;',
              'if(nhr_last_consumed_valid && (nhr_last_consumed&65535)==sequence)return;')
    text=once(text,'if((nhr_previous->sequence&65535)!=sequence||nhr_previous->sequence==nhr_last_consumed){',
              'if((nhr_previous->sequence&65535)!=sequence||\n'
              '       (nhr_last_consumed_valid&&nhr_previous->sequence==nhr_last_consumed)){')
    text=once(text,'    nhr_last_consumed=nhr_previous->sequence;',
              '    nhr_last_consumed=nhr_previous->sequence;nhr_last_consumed_valid=1;')
    text=once(text,'    nhr_used=0;nhr_put(0x4e54);nhr_put((++pk_nhr_sequence)&65535);',
              '    nhs_transport_started=1;\n'
              '    nhr_used=0;nhr_put(0x4e54);nhr_put((++pk_nhr_sequence)&65535);')
    text=once(text,'#include "'+str(previous)+'"','#include "'+str(target)+'"')
    text=once(text,'static void nhr_finish_previous(void)',
              'static void nhb_snapshot_receive(unsigned total);\nstatic void nhr_finish_previous(void)')
    text=once(text,'    if(offset!=total)pk_nhr_failures++;\n    pk_nhr_consumed++;',
              '    if(offset!=total)pk_nhr_failures++;\n    nhb_snapshot_receive(total);\n    pk_nhr_consumed++;')
    text=once(text,'nhr_put((seg->end-seg->start)|(mode<<5)|(seg->reset<<7)|(seg->mute<<8)|(seg->epoch_reset<<9));',
              'nhr_put((seg->end-seg->start)|(mode<<5)|(seg->reset<<7)|(seg->mute<<8)|(seg->epoch_reset<<9)|nhb_request_flag(apply));')
    text=once(text,'nhr_put((s->end-s->start)|(1u<<10)|(s->epoch_reset<<9));',
              'nhr_put((s->end-s->start)|(1u<<10)|(s->epoch_reset<<9)|nhb_request_flag(half));')
    return text
