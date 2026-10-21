// Minimal ot::Machine for compiling an unmodified copy of ot_emu's v4e.cpp
// into cf_cycle_bench: v4e.cpp needs only getCpuState, read8/read16 and
// write32 from its machine.
#pragma once
#include "mc68k/mc68k.h"
namespace ot
{
	class Machine : public mc68k::Mc68k
	{
	public:
		explicit Machine(unsigned _type) : Mc68k(_type) {}
		void write32(uint32_t _a, uint32_t _v) { write16(_a, uint16_t(_v >> 16)); write16(_a + 2, uint16_t(_v)); }
	};
}
