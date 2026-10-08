"""Exact v1.2.1 Karplus init/trigger/control state preparation."""
from __future__ import annotations
import struct
import karplus_control_update as k
import simple_drum_control as ctl
PANEL_TO_FIRMWARE=(1,0,2)
DEFAULT_WAVE=0x080222A0
SIMPLE_OSC_RENDER=0x0802819D

def p16(b,o,v): struct.pack_into('<H',b,o,v&0xffff)
def p32(b,o,v): struct.pack_into('<I',b,o,v&0xffffffff)
def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def _rate(offset,scale,param):
    den=48*(offset+1)+((48*(scale-1)*(param&0xffff))>>12)
    return 0 if den==0 else 0xfffff//den

def fresh_state(panel_mode:int,*,velocity:int=255,note:int=45)->bytearray:
    b=bytearray(0x10e0)
    b[5]=PANEL_TO_FIRMWARE[max(0,min(2,int(panel_mode)))]
    b[6]=max(1,min(255,int(velocity))); b[7]=max(0,min(127,int(note)))
    p32(b,0x38,DEFAULT_WAVE);p32(b,0x3c,DEFAULT_WAVE);p32(b,0x58,SIMPLE_OSC_RENDER)
    p32(b,0x60,0x00020000); p16(b,0xa8,0x0800)
    b[0x7a]=1;b[0x7c]=1
    p32(b,0x8c,0x00020001);p32(b,0x90,0x1c700032)
    p16(b,0x94,_rate(1,2,ctl._time_parameter(u16(b,0x0a))))
    p16(b,0x96,_rate(50,7280,ctl._time_parameter(0)))
    return b

def trigger(b:bytearray,*,velocity:int=255,note:int=45)->None:
    b[6]=max(1,min(255,int(velocity)))
    if note:b[7]=max(0,min(127,int(note)))
    b[0x84]=1;b[0x74]=1
    if b[0x7c]:p32(b,0x80,0)
    p16(b,0xc4,0);p32(b,0x10d8,0)

class ControlState:
    def __init__(self):self.targets=[0,0,0,0];self.last_raw=None;self.panel_mode=None
    def prepare(self,b,raw_values,panel_mode,pitch,chromatic,*,trig):
        raw_values=tuple(max(0,min(127,int(v))) for v in raw_values); panel_mode=max(0,min(2,int(panel_mode)))
        dirty=self.last_raw!=raw_values or self.panel_mode!=panel_mode
        if dirty:
            b[:]=k.karplus_update(bytes(b),self.targets,pitch,chromatic)
            b[:]=k.karplus_update(bytes(b),self.targets,pitch,chromatic)
            b[5]=PANEL_TO_FIRMWARE[panel_mode]
            self.targets=[ctl.panel_to_target(v) for v in raw_values]
            for _ in range(16): b[:]=k.karplus_update(bytes(b),self.targets,pitch,chromatic)
            self.last_raw=raw_values;self.panel_mode=panel_mode
        if trig:
            trigger(b)
            b[:]=k.karplus_update(bytes(b),self.targets,pitch,chromatic)
