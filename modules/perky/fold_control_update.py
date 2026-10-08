"""Exact v1.2.1 Fold Drum 1/2 state preparation for the ColdFire path.

Translated from original ARM routines:
  common init/update/trigger 0x080246ac / 0x08024714 / 0x08024878
  Fold1 init/trigger/update   0x080250d4 / 0x08025128 / 0x08025140
  Fold2 init/trigger/update   0x08024d94 / 0x08024e0c / 0x08024e54

No firmware table bytes are embedded. Callers supply pitch/chromatic tables.
"""
from __future__ import annotations
import struct
import karplus_control_update as common
import simple_drum_control as control

MASK32=0xffffffff
FOLD_PANEL_TO_FIRMWARE=(1,2,0) # no transient / noise / pulse
DEFAULT_WAVE=0x080222A0
SIMPLE_OSC_RENDER=0x0802819D


def u16(b,o): return struct.unpack_from('<H',b,o)[0]
def u32(b,o): return struct.unpack_from('<I',b,o)[0]
def p16(b,o,v): struct.pack_into('<H',b,o,v&0xffff)
def p32(b,o,v): struct.pack_into('<I',b,o,v&MASK32)

def _rate(offset:int,scale:int,param:int)->int:
    den=48*(offset+1)+((48*(scale-1)*(param&0xffff))>>12)
    return 0 if den==0 else 0xfffff//den

def _time(v:int)->int: return control._time_parameter(v)

def _init_common(size:int)->bytearray:
    b=bytearray(size)
    # Common cVoice init 0x080246ac.
    p32(b,0x38,DEFAULT_WAVE); p32(b,0x3c,DEFAULT_WAVE)
    p32(b,0x58,SIMPLE_OSC_RENDER)
    p32(b,0x60,0x00020000)  # noise count=0, reload=2
    p16(b,0xa8,0x0800)      # filter damping from helper 0x080288c0
    b[0x7a]=1; b[0x7c]=1
    p32(b,0x8c,0x00020001)  # attack cfg: offset=1 scale=2
    p32(b,0x90,0x0fa00019)  # default decay cfg before family override
    # common envelope initially receives a=d=0x1000
    p16(b,0x94,_rate(1,2,0x1000)); p16(b,0x96,_rate(25,4000,0x1000))
    return b

def _init_pitch_env(b:bytearray)->None:
    # Fold second envelope at +0xc4, 0x080250d4 / 0x08024d94.
    b[0xc5]=1; b[0xca]=1; b[0xcc]=1
    p32(b,0xdc,0x00010000)  # attack cfg offset=0 scale=1
    p32(b,0xe0,0x03e80000)  # decay cfg offset=0 scale=1000
    p16(b,0xe4,_rate(0,1,0x1000)); p16(b,0xe6,_rate(0,1000,0x0800))

def fresh_fold1(panel_mode:int,*,velocity:int=255,note:int=45)->bytearray:
    b=_init_common(0xf4); _init_pitch_env(b)
    b[5]=FOLD_PANEL_TO_FIRMWARE[max(0,min(2,int(panel_mode)))]
    b[6]=max(1,min(255,int(velocity))); b[7]=max(0,min(127,int(note)))
    b[0x7c]=0
    p32(b,0x90,0x1c700032) # amp decay cfg offset=50 scale=7280
    # recompute amp rates using Fold cfg; +0x0a is still zero at init.
    p16(b,0x94,_rate(1,2,_time(u16(b,0x0a))))
    p16(b,0x96,_rate(50,7280,_time(0)))
    return b

def fresh_fold2(panel_mode:int,*,object_address:int=0x20000000,velocity:int=255,note:int=45)->bytearray:
    b=_init_common(0x134); _init_pitch_env(b)
    b[5]=FOLD_PANEL_TO_FIRMWARE[max(0,min(2,int(panel_mode)))]
    b[6]=max(1,min(255,int(velocity))); b[7]=max(0,min(127,int(note)))
    b[0x7c]=0; p32(b,0x90,0x1c700032)
    p16(b,0x94,_rate(1,2,_time(u16(b,0x0a))))
    p16(b,0x96,_rate(50,7280,_time(0)))
    # second simple oscillator initialized at +0xf4
    p32(b,0x100,DEFAULT_WAVE); p32(b,0x104,DEFAULT_WAVE)
    p32(b,0x120,SIMPLE_OSC_RENDER)
    p32(b,0x128,object_address+0x2c); p32(b,0x12c,object_address+0xf4)
    return b

def _env_trigger(b:bytearray,base:int)->None:
    b[base+0x10]=1; b[base]=1
    if b[base+8]: p32(b,base+0x0c,0)

def trigger_fold1(b:bytearray,*,velocity:int=255,note:int=45)->None:
    b[6]=max(1,min(255,int(velocity)))
    if note: b[7]=max(0,min(127,int(note)))
    _env_trigger(b,0x74); _env_trigger(b,0xc4); p16(b,0xec,0)

def trigger_fold2(b:bytearray,*,object_address:int=0x20000000,velocity:int=255,note:int=45)->None:
    trigger_fold1(b,velocity=velocity,note=note)
    old=b[0xf2]; b[0xf2]=0 if old else 1
    a=object_address+0x2c; z=object_address+0xf4
    if old==0: primary,secondary=z,a
    else: primary,secondary=a,z
    p32(b,0x128,primary); p32(b,0x12c,secondary)
    p32(b,(primary-object_address)+4,0)
    p16(b,0x132,u16(b,0x130))

def update(b:bytearray,targets,pitch:bytes,chromatic:bytes):
    prepared=common.common_update(b,targets,pitch,chromatic)
    p16(b,0xee,u16(b,0xc0)) # Param2 pitch-envelope amount
    p16(b,0xf0,u16(b,0xbe)) # Param1 fold amount
    return prepared

class ControlState:
    def __init__(self):
        self.targets=[0,0,0,0]; self.last_raw=None; self.panel_mode=None
    def prepare(self,b:bytearray,raw_values,panel_mode,pitch,chromatic,*,trig:bool,fold2:bool=False,object_address:int=0x20000000):
        raw_values=tuple(max(0,min(127,int(v))) for v in raw_values); panel_mode=max(0,min(2,int(panel_mode)))
        dirty=self.last_raw!=raw_values or self.panel_mode!=panel_mode
        if dirty:
            update(b,self.targets,pitch,chromatic); update(b,self.targets,pitch,chromatic)
            b[5]=FOLD_PANEL_TO_FIRMWARE[panel_mode]
            self.targets=[control.panel_to_target(v) for v in raw_values]
            for _ in range(16): update(b,self.targets,pitch,chromatic)
            self.last_raw=raw_values; self.panel_mode=panel_mode
        if trig:
            if fold2: trigger_fold2(b,object_address=object_address)
            else: trigger_fold1(b)
            update(b,self.targets,pitch,chromatic)
