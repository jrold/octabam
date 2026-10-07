"""Candidate Fold 1 prepared record, sharing the qualified smoother cadence.

Amplitude config (50, 7280) is from v1.2.1 init at 0x08025124.
Pitch envelope decay remains its fixed init value 43; sample hold reload is 2.
"""
from dataclasses import dataclass
import simple_drum_transport as common
import simple_drum_control as ctl

@dataclass
class State(common.State):
    def prepare(self,raw,mode,*,trigger):
        record=bytearray(super().prepare(raw,mode,trigger=trigger))
        values=[ctl._envelope_decay_rate(ctl._time_parameter(self.prepared[1]),50,7280),self.prepared[2],self.prepared[3]]
        for i,value in enumerate(values):record[2+2*i:4+2*i]=int(value).to_bytes(2,'big')
        record[11]=0
        return bytes(record)
